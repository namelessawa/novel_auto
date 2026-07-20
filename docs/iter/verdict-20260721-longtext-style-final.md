# 长文本与多题材风格自我迭代：最终报告

## 1. 执行摘要

- 分支：`codex/longtext-style-iteration-20260721`
- Git 基线：`a3e1398ff1457e6f97d816d564f90cdedeee4de3`
- 最终实现 SHA（总报告之前）：`6477f61b3ade9f3e984f66f457521976106edac9`
- 主模型：`glm-5.2`；`ark-code-latest` 已弃用且未用于有效实验。
- 备用 `deepseek-v4-pro` 只留下独立的早期部分样本，不与 GLM 结果混合。
- 完成 6 轮有效迭代：4 轮接受测量/确定性改进，2 轮质量候选拒绝并完整回滚。
- 没有修改 Narrator 产出策略、生产风格默认、StateGuard 阈值、`old/`、生产数据，
  也没有 push、PR 或部署。

本轮解决了四个可证实问题：非法 cast 在校验前调用 LLM；D2/D3/D4/D5/D6/D8
缺字段时制造假健康/假告警；缺少真正隐藏标签的多类风格盲测；style benchmark
不记录按 agent 的 Token 与时延。

没有解决的核心质量问题：4-Tick 压力序列仍只有 `6/12` 正文被状态复验保留；
哲思风格在两个题材都被盲判为冷峻；压力场景风格辨识明显弱于兼容场景；当前 SHA
没有完成 30–50 Tick 三 seed、200 Tick 或 500 Tick 验证。因此不修改全局默认值。

## 2. 审计与基线

### 2.1 仓库审计摘要

1. 长文本上下文：Narrator 已接收正文尾部、世界/角色状态与行动、`known_facts`、
   reader knowledge、OpenLoop、优先长期记忆、风格快照和上一段
   `continuity_state`。缺口是 SummaryTree 的节/卷/root 摘要没有形成明确的 Tick
   Narrator 分层上下文链。
2. 事实复验：`visible_to/known_facts` → ActionResolver/StatePatch → Narrator
   → bounded critic → NarrativeStateGuard（二次复验）→ snapshot preflight → 周期
   ConsistencyGuardian。FactLedger 尚未统一登记物品、数量、伤势、关系和知识来源；
   周期 Guardian 主要看摘要而非完整正文。
3. 分层记忆：PriorityMemoryStore 有 L0–L3、protected 与相关性检索；Compressor
   50/500/5000 Tick 分层压缩；SummaryTree 可原子持久化，但主 Tick 消费链不足。
4. 风格契约：key/version/full snapshot/prompt hash 随小说冻结；旧小说优先使用
   snapshot。theme 与 style 数据结构分离。生产 SectionEditor 采纳后仍缺独立 style
   复验。
5. benchmark/judge：现有 cost、quality、D1–D8、style compatible/pressure、
   checkpoint/resume 基础完整；本轮补齐缺失值语义、逐 Tick 状态字段、盲分类和
   style cost。

完整初始审计见 `docs/iter/verdict-20260721-longtext-style-baseline-inconclusive.md`；
其中 provider 不可用是当时状态，已被后续 GLM 实跑更新，本报告为最终结论。

### 2.2 环境指纹

| 项目 | 值 |
| --- | --- |
| Python | 3.11.15 |
| Node | 24.11.0 |
| npm | 11.14.1 |
| provider | `custom`（来自被 gitignore 的 `coding.txt`） |
| model | `glm-5.2` |
| registry | 21 themes / 16 styles，动态读取 |
| style schema | `2026-07-15.5`，生产 preset 最终未改变 |
| secrets | 只记录变量名/存在性；未记录凭据值 |

### 2.3 Gate A 与构建

| 指标 | Baseline | Final |
| --- | ---: | ---: |
| 后端测试 | 1209 passed / 1 failed | 1224 passed / 0 failed |
| warning | 1 | 1（既有 Starlette/httpx 弃用） |
| 前端生产构建 | PASS | PASS |
| 前端模块 | 55 | 55 |
| JS | 320.55 kB / gzip 95.20 kB | 同左 |

### 2.4 三题材 3-Tick 真实 GLM baseline

| Theme | Tokens | Calls | Bootstrap s | Avg Tick s | Narrated | StateGuard tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `republic_spy` | 15,102 | 5 | 121.86 | 22.37 | 1/3 | 9,395 (62.2%) |
| `gourmet_culinary` | 8,425 | 3 | 118.35 | 11.74 | 0/3 | 2,756 (32.7%) |
| `apocalypse_wasteland` | 20,950 | 7 | 117.20 | 29.45 | 0/3 | 15,141 (72.3%) |

三份 3-Tick 只能建立成本/短程行为基线，不能证明长程稳定。修复后的 analyzer 会把
缺 critic 数据显示为 unknown，把已有 Token/OpenLoop snapshot 回填，并且不再要求
未到 50 Tick 的 MemoryCompressor 运行。

### 2.5 风格与连续性 baseline

- 单 Tick 目标已知契约 judge：`9/12` accepted；compatible `6/6`，pressure
  `3/6`。pressure 失败为 `noir_cold`、`warm_healing`、
  `philosophical_meditative`。
- 匿名全候选盲测：valid `12/12`；Top-1 `6/12 = 50.00%`；Top-3
  `7/12 = 58.33%`。
- pressure：Top-1 `2/6`，Top-3 `3/6`；compatible：Top-1/Top-3 均 `4/6`。
- 两次盲测聚合完全一致，但完整排名有 `2/12` 变化，说明 judge 仍有方差。
- 4-Tick 压力序列：完整样本 `0/3` accepted，正文保留 `6/12`；literary
  `3/4`、first-person `2/4`、ensemble `1/4`。

## 3. 迭代记录

| # | 假设/最小改动 | 结果 | 决策 |
| --- | --- | --- | --- |
| 01 | partial cast 校验前移到首次 LLM 前 | 非法输入真实调用从 ≥1 降为 0；合法路径不变 | ACCEPT |
| 02 | bench/analyzer schema 缺失值与实际字段错位 | D2 unknown、D3/D5/D6 可回填；短 bucket 不再误报 D4/D8 | ACCEPT |
| 03 | 扩展 StateGuard 对雨损、多人过门、债务的中文证据识别 | 两版 candidate 都是 0/3、6/12；不同风格随机升降 | REJECT；完整回滚 |
| 04 | 增加匿名全候选 style classifier | 首次得到 Top-1/Top-3/混淆矩阵；增加 50k fail-closed 预算 | ACCEPT（测量） |
| 05 | 强制哲思“具体物→概念问题→选择”链 | 目标已知 judge 1/2→2/2，但盲测仍 0/2 Top-3 | REJECT；完整回滚 |
| 06 | validate_styles 复用 TokenBudgetTracker 拍成本快照 | smoke 1/1 覆盖；23,409 tokens 全部归因，missing=0 | ACCEPT（测量） |

各轮结构化记录见 `docs/iter/iteration-02-*.md` 至 `iteration-06-*.md`；Iteration 01
记录在初始审计报告。拒绝候选的原始 JSON、正文、judge 与复验 trace 均保留。

## 4. 最终对比

| 维度 | Baseline | Final | 解释 |
| --- | --- | --- | --- |
| 非法 cast 外部调用 | ≥1 | 0 | 确定性修复 |
| D2 无数据 | 100% clean | unknown / 0 evaluated | 消除假健康 |
| 3-Tick D4/D8 | 假告警 | 不告警 | 周期/短桶语义修复 |
| cumulative tokens | null | 从 tick delta 重建 | 测量修复 |
| OpenLoop average | null | 从 snapshots 重建 | 测量修复 |
| 盲 style Top-1/Top-3 | 未测 | 50.00% / 58.33% | 新基线，不是质量提升 |
| style cost coverage | 0% | smoke 100% | 新测量能力 |
| 生产 Narrator/Style 默认 | 基线 | 相同 | 两个质量候选均回滚 |
| 4-Tick 保留率 | 6/12 | 6/12 | 无稳定质量改善 |

不存在可诚实展示的“同 seed 最终正文胜过 baseline”案例：所有生成侧候选都因同模型、
同场景对照未稳定改善而回滚。最终版本的收益是更可靠的状态边界与测量证据，不是
伪造的文风得分增长。

Iteration 06 的独立成本 smoke：bootstrap `10,121` Token/96.672s；样本
`13,288` Token/64.503s；总计 `23,409` Token，8 calls。样本中 Narrator
`5,790`、State Verifier `3,802`、style anchors `2,175`、semantic judge
`1,521`；`unattributed=0`。

## 5. 最差案例

1. 4-Tick ensemble：最终只保留 `1/4`。候选在屋顶/城墙终态、地图持有者与损坏
   原因上出现歧义；StateGuard 拒绝是必要的，但两次修复未稳定救回。
2. 哲思候选：pressure 明写“他扣的不是通行证。他扣的是时间”，目标已知 judge
   通过；匿名 judge 仍判 `noir_cold, rough_grit_realism, xianxia_fast`。兼容
   科幻样本也判 `noir_cold, literary, melancholic`，两段均未进 Top-3。
3. warm-healing 压力样本：匿名 Top-3 为 `rough_grit_realism, noir_cold,
   literary`，说明末日压力把照料/关系节奏压成肉身负担和冷峻动作。
4. StateGuard evidence candidate：两轮 aggregate 均为 `6/12`，但 literary、
   first-person、ensemble 的保留率互相升降；这证明扩 regex 只追逐随机措辞。

## 6. 风险与未满足验收

- 当前 SHA 未完成三个 seed 的 30–50 Tick Gate C，也未完成 200 Tick Gate D。
- 未准备修改生产默认，因此没有为当前 SHA 运行 500 Tick Gate E。仓库 6 月的
  200/500-Tick 文件来自旧 SHA/旧模型，只作成本参照，不能冒充本轮验收。
- 历史 200 Tick 单 run 已消耗约 106 万 Token；按当前短跑外推，3 seed × 3 题材
  的 200 Tick 是数百万 Token和数小时，触发“下一步显著增加费用”的停止条件。
- 同模型生成/判分有自偏；盲候选契约也可能过于显式；12 样本置信区间很宽。
- GLM API 不回显可审计的采样 seed；注册表 seed 固定不等于模型采样字节级复现。
- SummaryTree 尚未成为 Tick Narrator 的真实节/章/卷上下文链。
- FactLedger、continuity_state、KnowledgeGraph 与摘要树仍缺统一 fact identity/source。
- StateGuard 成本占比高，但当前没有足够误报证据支持降低强度。
- 没有数据 migration；风格生产版本/hash 最终未变。未来升级必须显式版本化。

## 7. 修改文件

没有删除文件，`old/` 未修改。净代码/测试改动：

- `backend/agents/orchestrator.py`：暴露并清空最近 Guardian 观测。
- `backend/bootstrap_prompts.py`：cast all-or-nothing 校验前移。
- `scripts/bench_tick.py`：逐 Tick critic/Guardian/OpenLoop/token/skip telemetry。
- `scripts/analyze_longrange_drift.py`：D2–D8 unknown、回填和短 bucket 语义。
- `scripts/classify_styles_blind.py`：匿名多类分类、checkpoint、预算、成本。
- `scripts/validate_styles.py`：bootstrap/sample 的按 agent 成本与覆盖率。
- `backend/tests/test_analyzer_measurement_coverage.py`
- `backend/tests/test_bench_script_smoke.py`
- `backend/tests/test_blind_style_classifier.py`
- `backend/tests/test_bootstrap_cast_size.py`
- `backend/tests/test_tick_throughput.py`
- `backend/tests/test_validate_styles_script.py`

新增实验/审计产物（JSON 与 Markdown 均纳入版本控制）：

```text
docs/iter/bench-baseline-glm-20260721-apocalypse_wasteland.{json,md}
docs/iter/bench-baseline-glm-20260721-gourmet_culinary.{json,md}
docs/iter/bench-baseline-glm-20260721-republic_spy.{json,md}
docs/iter/bench-candidate-measurement-glm-20260721-republic_spy.{json,md}
docs/iter/blind-style-baseline-glm-20260721.{json,md}
docs/iter/blind-style-baseline-glm-trial1-pre-token-fix-20260721.{json,md}
docs/iter/blind-style-candidate-philosophical-glm-20260721.{json,md}
docs/iter/drift-baseline-glm-20260721-apocalypse_wasteland.md
docs/iter/drift-baseline-glm-20260721-gourmet_culinary.md
docs/iter/drift-baseline-glm-20260721-republic_spy.md
docs/iter/drift-candidate-measurement-glm-20260721-republic_spy.md
docs/iter/iteration-02-measurement-telemetry-20260721.md
docs/iter/iteration-03-state-evidence-false-positive-20260721.md
docs/iter/iteration-04-blind-style-classification-20260721.md
docs/iter/iteration-05-philosophical-observable-chain-20260721.md
docs/iter/iteration-06-style-cost-telemetry-20260721.md
docs/iter/style-baseline-glm-20260721.{json,md}
docs/iter/style-candidate-philosophical-glm-20260721.{json,md}
docs/iter/style-cost-telemetry-smoke-glm-20260721.{json,md}
docs/iter/style-sequence-baseline-glm-20260721.{json,md}
docs/iter/style-sequence-candidate-state-evidence-glm-20260721.{json,md}
docs/iter/style-sequence-candidate-state-evidence-v2-glm-20260721.{json,md}
docs/iter/style-sequence-fallback-deepseek-20260721.json
docs/iter/verdict-20260721-longtext-style-baseline-inconclusive.md
docs/iter/verdict-20260721-longtext-style-final.md
```

被拒绝的 `narrative_state_guard.py` 与哲思 preset 改动已由 revert 恢复，因而不在
最终净改动列表；对应 commit 和失败产物仍可审计。

## 8. 验证命令

```powershell
git switch codex/longtext-style-iteration-20260721

python -m pytest backend/tests/ -v
Push-Location frontend
npm run build
Pop-Location

python scripts/bench_tick.py --help
python scripts/validate_styles.py --help
python scripts/analyze_longrange_drift.py --help
python scripts/compare_bench.py --help
python scripts/classify_styles_blind.py --help

python scripts/analyze_longrange_drift.py `
  docs/iter/bench-baseline-glm-20260721-republic_spy.json

python scripts/classify_styles_blind.py `
  --input docs/iter/style-baseline-glm-20260721.json `
  --provider-file coding.txt `
  --sample-styles xianxia_fast,noir_cold,warm_healing,ensemble_epic,philosophical_meditative,rough_grit_realism `
  --judge-budget 60000 `
  --out docs/iter/blind-style-baseline-glm-20260721.json

python scripts/validate_styles.py `
  --provider-file coding.txt `
  --mode compatible `
  --styles rough_grit_realism `
  --ticks 1 `
  --max-revisions 0 `
  --out docs/iter/style-cost-telemetry-smoke-glm-20260721.json
```

命令只引用 `coding.txt` 路径，不打印其内容。复跑真实模型会产生费用且可能因 provider
随机性得到不同正文；必须保留全部 seed/场景，不得只挑最佳输出。

## 9. 最终结论

`CONDITIONAL PASS：局部有效，但尚不应修改全局默认值。`

理由：确定性校验与三类测量工具有充分测试和真实 smoke 证据；生成质量候选均已按
规则回滚。缺少当前 SHA 的跨 seed 30–50 Tick、200 Tick 和长期风格漂移证据，不能
声称长篇质量已经提升，也不能采用新的生产风格或 StateGuard 默认。
