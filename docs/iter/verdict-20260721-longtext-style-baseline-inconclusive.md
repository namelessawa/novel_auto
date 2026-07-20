# 长文本与多题材风格自我迭代：审计、基线与停止报告

## 实验记录

```text
iteration_id: 20260721-01-bootstrap-cast-preflight
date: 2026-07-21
base_git_sha: a3e1398ff1457e6f97d816d564f90cdedeee4de3
candidate_git_sha: cd7e9edf8dbcd4111de8babbef49806a8bdbf711
hypothesis: cast 参数的 all-or-nothing 校验位于首次 LLM 调用之后，导致非法输入产生真实请求；将原校验前移到 bootstrap_world 入口即可消除外部调用且不改变合法配置。
files_changed: backend/bootstrap_prompts.py; backend/tests/test_bootstrap_cast_size.py
tests_added: test_bootstrap_world_partial_cast_raises 增加“任何 LLM 调用都立即失败”的回归断言
provider: custom（coding.txt；仅记录类型，不记录 URL 或凭据）
model: glm-5.2；授权回退探针 deepseek-v4-pro
themes: 未运行真实生成
styles: 未运行真实生成
seeds: 未运行真实生成
tick_counts: 0（provider preflight 失败）
baseline_metrics: 初始全量 1209 passed / 1 failed；前端构建通过
candidate_metrics: 定向 13 passed；全量 1210 passed；前端构建通过
failure_samples: 非法 partial cast 在修复前越过确定性边界并触发真实 WorldState 请求
cost_delta: 非法输入由至少 1 次 LLM 请求降为 0；合法生成路径无成本变化
verdict: ACCEPT
rollback_status: 未回滚；可用 git revert cd7e9ed 回滚
next_recommendation: provider 恢复后先修 benchmark D2/D3/D5/D6 数据链，再跑同配置 baseline
```

本轮总控结论：`INCONCLUSIVE`。唯一接受的改动是确定性输入校验修复，不构成小说质量提升证据。

## 安全环境指纹

- 分支：`codex/longtext-style-iteration-20260721`
- 基线 SHA：`a3e1398ff1457e6f97d816d564f90cdedeee4de3`
- Python：3.11.15
- Node：24.11.0
- npm：11.14.1
- `coding.txt`：存在且被 `.gitignore` 排除；仅确认 `KEY`、`URL`、`MODEL` 三个变量存在。
- 配置模型：`glm-5.2`。没有记录 URL、KEY 或任何凭据值。
- 关键调参环境变量在启动 shell 中均未显式设置：`LLM_PROVIDER`、critic gates、open-loop cap、并发数、Narrator/StateGuard 开关、token cap、timeout 和 judge model 均走代码默认或项目配置加载链。
- 注册表动态读取：21 个 theme、16 个 style；style schema 版本均为 `2026-07-15.5`，本轮未复制注册表列表到新代码。

## 仓库审计

### 1. 当前长文本上下文链路

`Orchestrator` 依次推进 WorldSimulator、EventInjector、角色决策、ActionResolver 和状态应用，再让 Narrator 与只读周期 agent 并行运行。Narrator 当前获得：

- 最近正文尾部（prompt 实际截取 800 字，进程恢复时先读取最近文件尾部 1500 字）；
- 当前 WorldState、场景角色状态、角色 profile、原始行动与对白；
- 角色 `known_facts` 所约束的行动结果和事件 `visible_to`；
- 上一段完整 `continuity_state`、读者已知事实、待答问题和最近兑现记录；
- urgency 排序后的开放伏笔、最近 5 条 tick 摘要/调度提示；
- PriorityMemoryStore 按重要性、时间邻近、角色重合、层级和保护状态选出的 top-5 长期记忆；
- 持久化的风格契约快照和 StyleAnchor。

缺口：Tick 主链的 `SummaryTree` 主要被持久化，未见 Narrator 注入 `root_summary`、卷摘要或节摘要；TickRuntime 中也未见把完成节写入该树的路径。Narrator 所谓 `recent_chapter_summaries` 实际混合 tick 摘要、警告与 hints，并非严格的节/章/卷层级上下文。

### 2. 当前事实与状态复验链路

- Event 的 `visible_to` 和 CharacterState 的 `known_facts` 构成角色信息边界。
- ActionResolver 与 StatePatch 在正文前确定性落世界状态。
- FactLedger 目前从角色行动登记位置和死亡事实，并在新事实进入时检测冲突。
- Narrator 先经过风格确定性 gate、bounded critic，再由 NarrativeStateGuard 对上一账本、正文、声明账本和源事件终态独立复验；最多两次外科修复，每次均重新验证，最终失败则 Narrator 沉默。
- Orchestrator 落盘前另有 snapshot preflight，并只对真正消费的事件登记读者事实、touch memory 和兑现伏笔。
- ConsistencyGuardian 每 30 Tick 复用 continuity_v2，同时有无 LLM 的 hallucination-rate 检查。
- SectionEditor 可在节边界消除重播/接缝，候选必须通过事实守恒验证；验证失败保留原始拼接稿。

缺口：FactLedger 没有系统登记 Narrator 账本中的物品、数量、伤势、关系和知识来源；ConsistencyGuardian 收到的是最近摘要而非逐 Tick 正文；生产 SectionCloser 在采纳 SectionEditor 后没有再次运行 style-contract gate。

### 3. 当前分层记忆与摘要树链路

- PriorityMemoryStore 持久化 L0-L3，检索分数包含 importance、recency、角色/标签重合、自由文本、tier 和 protected bonus。
- 显著事件以事件 ID 进入 L0；Narrator 消费事件后 touch；OpenLoop 的 origin event 会被 mark protected。
- MemoryCompressor 每 50 Tick 处理 L0→L1，500 Tick 后 L1→L2，5000 Tick 后尝试 L2→L3；压缩成功后用 `source_ids` 原子替换旧条目。
- SummaryTree 支持节叶、卷合并、root summary、legend 和原子持久化。

缺口：L2→L3 用 MemoryEntry ID 代理 SummaryTree node ID，二者并不保证存在映射；更重要的是 Tick 主链没有消费 SummaryTree 的节/卷/root 层，因此“树存在”不等于“长文上下文实际利用”。

### 4. 当前风格契约与持久化

- StylePreset 明确区分 key、版本、完整 snapshot、det rules、strict cadence、冲突策略和 SHA-256 `prompt_hash`。
- TickState 冻结旧作品 snapshot；Narrator 优先从 snapshot 恢复，不会因注册表升级静默改变旧小说。
- 风格 addendum 和 StyleAnchor 放在 user prompt，system prompt 保持稳定 prefix；长 prompt 尾部再放短 checklist。
- production 在严格节拍运行确定性规则，高等级违约最多定向重写一次；StateGuard 在风格/critic 之后复验事实。

缺口：现有 semantic style judge 明示 style label/key/contract，不是真正盲分类；没有 top-1/top-3、混淆矩阵或跨题材 StyleAnchor 距离；生产 SectionEditor 后没有 style 复验。

### 5. 当前 benchmark、judge 与确定性指标

- `bench_tick.py` 记录总 token、prompt/completion/cache token、按 agent/priority 分解、逐 Tick 时延、Narrator 字数、agents called、event IDs、open-loop snapshots 和 novelty records；支持 theme/style 注册表参数、多 theme、checkpoint 与可选 quality。
- quality 路径当前集成 repetition、final-snapshot 近似 consistency、compliance 和可选 rubric judge；pairwise runner 有 A/B 随机换位和 prompt/model 元数据。
- `validate_styles.py` 支持 compatible/pressure、序列、SectionEditor、事实复验、0-2 次修订、checkpoint/resume 和 style hash。
- `analyze_longrange_drift.py` 保留 D1-D8；quality_metrics 目录还包含 prose dynamics、character signal、translation artifact、section closing/seams、sense diversity 等确定性指标。

测量盲区：当前 `bench_tick.py` 的 `per_tick` 没有 `critic_surviving_codes`、`open_loop_count`、`contradiction_count` 或 cumulative token。分析器也没有从已有 `tick_total_tokens` 与 `open_loop_snapshots` 回填：

- D2 的 clean rate 对缺字段记录会显示 100%，不能测量 critic 退化；
- D3 看不到已经另行保存的 open-loop snapshots；
- D5 没有矛盾累计字段；
- D6 忽略 `tick_total_tokens`，cumulative slope 为 null；
- 历史旧 schema 还缺 `narrator_produced` 和 `agents_called`，因此 D4/D7 只能部分工作。

### 6. 已经解决的问题

- v1 章节式单体链已归档，多 Agent Tick 架构保持完整。
- 选择性叙述、角色视野、ActionResolver、原子状态写、SQLite WAL、知识图谱和 reader API 已落地。
- 成本质量循环历史上把 3-Tick+bootstrap token 从 137,890 降到稳定约 31,214，同时限制 critic 轮次。
- OpenLoop 累积、stale 线索、行政关闭、cast 固定过拟合、sustained climax、reasoning leak、schema placeholder、SummaryTree/MemoryStore 持久化等已有回归保护。
- 单 Tick 风格 compatible/pressure 历史人工验收为 32/32；风格 snapshot/hash 已持久化。
- 本轮修复非法 partial cast 在校验前调用 LLM 的确定性缺陷。

### 7. 仍存在的实现缺口或测量盲区

1. 长程 D2/D3/D5/D6 数据链当前不可用，历史“WARN/PASS”只覆盖实际有数据的信号。
2. 4-Tick 代表性压力回归的历史最终结果仍为 0/3，StateGuard 正确拒错，但可用正文救回率不足。
3. 源事件终态仍主要是自然语言 consequences，复合人物集合、目标位置、物品持有者/数量/损坏原因和新代价类型依靠脆弱解析。
4. FactLedger、continuity_state、KnowledgeGraph、SummaryTree 与正文没有统一的可追溯 fact identity/source contract。
5. SummaryTree 未进入 Tick Narrator 的实际分层上下文选择。
6. Style judge 非盲测，没有 confusion matrix；长期采样点和 StyleAnchor 距离未自动化。
7. 当前成本报告缺 StateGuard repair 尝试/救回/误报/放弃及独立耗时；“每千字有效正文成本”未直接输出。

### 8. 最值得优先验证的三个假设

1. 先补齐 D2/D3/D5/D6 的逐 Tick telemetry，并让 analyzer 对新旧 schema 都 fail-closed，能够揭示此前被 100% clean/null 掩盖的长程退化；这是下一轮首要测量工作。
2. 把 required end state 改为结构化、带 entity/source/effective tick/knowledge scope 的契约，可减少 NarrativeStateGuard 对自然语言证据的误杀，并提高一次/二次 repair 的真实救回率。
3. 真正隐藏 style key/label 的全候选分类器，加跨 theme 的 top-1/top-3/confusion matrix 和 1/10/25/50/100/200 Tick 采样，会证明单 Tick 32/32 是否只是契约可见或开场效应。

## 当前基线

### Gate A

- 初次全量：1209 passed，1 failed，1 warning，44.37 秒。
- 失败：`test_bootstrap_world_partial_cast_raises` 越过输入校验调用真实模型。
- 修复后定向：13 passed。
- 修复后全量：1210 passed，1 个既有 Starlette/httpx 弃用 warning，31.18 秒。
- 前端生产构建：55 modules，JS 320.55 kB（gzip 95.20 kB），通过。
- 四个脚本的 `--help` 均通过；theme/style 参数来自注册表。

### Provider preflight

- `glm-5.2`：约 3 秒返回 HTTP 400 `InvalidSubscription`。
- 同凭据仅切换 `deepseek-v4-pro`：约 3 秒返回同一 `InvalidSubscription`。
- 结论：不是 GLM 卡顿或单模型不兼容，是订阅不可用；没有进入 Gate B/C/D/E。

### 仅作历史参照的现有产物（不是当前 candidate 实跑）

| Artifact | Completed | Tokens | Narrate rate | Avg sec | P95 sec |
|---|---:|---:|---:|---:|---:|
| Phase 5-J 200 Tick | 200/200 | 1,062,459 | 43.5% | 63.97 | 218.99 |
| Phase 6-A steampunk retry | 500/500 | 3,023,064 | 48.2% | 36.02 | 135.34 |
| Phase 6-A republic | 500/500 | 1,897,219 | 32.4% | 22.27 | 93.42 |
| Phase 6-A apocalypse artifact | 290/500 | 3,006,585 | 60.0% | 47.93 | 134.67 |

当前 analyzer 重跑 steampunk 历史文件只报 D1×2；D2 显示恒 100%，D3/D5/D6 为 null，证明上述 schema 盲区。历史单 Tick风格报告 32/32 accepted；历史 4-Tick 代表序列 0/3 accepted。

## 最差案例（历史合成 benchmark，不冒充本轮生成）

1. `literary`：源事件要求两人越过出口、后续到达城墙外且地图由雨水损坏；历史候选缺少两人越界证据，后续停在屋顶逃生梯并用错误原因损图。StateGuard 拒绝正确，但两次修订未救回。
2. `first_person_immersive`：历史候选用垃圾堆积水替代指定雨水损图，把委员会发言权这种收益当“新代价”，并凭空引入旧识专名。风格有限视点成立，事实契约失败。
3. `ensemble_epic`：历史候选无下雨事件却把完好地图改成雨损，又把既定地图付款重复算作新代价。视点轮换成立，终态与因果失败。

对应原始 trace 和正文保存在 `style-sequence-final-v3-20260715.json`，人工判读在 `style-sequence-validation-manual-20260715.md`。

## 风险与停止理由

- Provider 随机性与 judge 偏差无法通过当前订阅状态重新量化。
- 历史 benchmark 来自更早 SHA/模型，不能作为当前分支质量验收。
- 单 Tick 风格通过不能外推长程；可见契约 judge 可能高估辨识度。
- 当前 drift analyzer 的缺字段默认会制造假 clean/null，修改默认值前必须修复。
- 没有执行数据迁移、部署、push、PR 或生产数据变更。
- 根据总控 Prompt 的停止条件“真实 LLM 不可用，无法完成质量验收”，停止继续迭代。

## 复现命令

```powershell
git switch codex/longtext-style-iteration-20260721
python -m pytest backend/tests/test_bootstrap_cast_size.py -v
python -m pytest backend/tests/ -v
Push-Location frontend
npm run build
Pop-Location
python scripts/bench_tick.py --help
python scripts/validate_styles.py --help
python scripts/analyze_longrange_drift.py --help
python scripts/compare_bench.py --help
python scripts/analyze_longrange_drift.py docs/iter/bench-phase6a-500tick-seed1-retry-0625.json
```

Provider 恢复后，先运行安全探针，再开始真实 baseline；不要在命令行回显凭据：

```powershell
python scripts/validate_styles.py --provider-file coding.txt --mode both --ticks 1 --no-judge --out docs/iter/style-baseline-restored.json
```

最终结论：`INCONCLUSIVE：受配额、模型或测量限制，证据不足。`
