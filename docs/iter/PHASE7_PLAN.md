# Phase 7 计划：统一事实链路、分层上下文与压力风格稳定性

## 范围与基线

- branch: `codex/longtext-style-iteration-20260721`
- 行为基线 SHA: `6477f61b3ade9f3e984f66f457521976106edac9`
- Phase 7 起始 HEAD: `8cb645be1f9713c085e5ef722ae91c55b75eed77`
- 差异说明: 起始 HEAD 只比行为基线多上一轮最终报告，不改变运行时代码。
- 上轮结论: `CONDITIONAL PASS`
- 主模型: `glm-5.2`
- 允许的卡顿回退: `deepseek-v4-pro`
- 禁用模型: `ark-code-latest`
- 最大有效迭代: 8
- 不在范围内: `old/`、不可逆迁移、生产数据、push、PR、部署、先改 StylePreset、先扩 StateGuard 正则。

## 已验证基线

| 项目 | 结果 |
| --- | --- |
| Python | 3.11.15 |
| Node | 24.11.0 |
| npm | 11.14.1 |
| 后端测试 | 1224 passed, 1 个既有 Starlette/httpx 弃用 warning |
| 前端生产构建 | PASS，55 modules，JS 320.55 kB / gzip 95.20 kB |
| 上轮 4-Tick 保留正文 | 6/12 |
| 上轮盲测 | Top-1 6/12，Top-3 7/12 |
| 未完成 | 当前 SHA 的跨 seed 30 Tick、200 Tick、500 Tick |

环境记录只保存 provider/model 和凭据变量是否存在，不保存凭据值。工作树中的未跟踪
`scripts/openai_compatible_chat.py` 不属于本任务，不读取、不修改、不提交。

## 仓库审计摘要

### 当前事实数据流

| 阶段 | 输入事实 | 输出事实 | 稳定 ID | 来源 | 有效期 | known_by | 持久化位置 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WorldSimulator | WorldState、近期事件、摘要 | 新 WorldState、自然 Event、字符串 consequences | Event 有 ID；状态字段无事实 ID | Event 自身可追踪；WorldState 字段无逐项来源 | 只有 tick 快照 | 无 | `tick_state.json`、`ticks.db` |
| EventInjector | WorldState、角色、OpenLoop、节奏建议 | Event、StatePatch | Event/StatePatch 可带 source_event_id；字段更新无 fact ID | StatePatch 可有 source_event_id，Event consequence 只是字符串 | 无逐事实有效期 | Event 仅有 visible_to | `ticks.db`；应用后进 `tick_state.json` |
| CharacterAgent | 自己的 CharacterState、合法可见 Event | CharacterAction、newly_learned/newly_speculated、状态 delta | Action 无稳定 fact ID | 获知字符串未绑定 Event；状态 delta 无来源字段 | 无 | 仅调用前按 visible_to 过滤 | 应用后进 `tick_state.json`、事件进 `ticks.db` |
| ActionResolver | 多角色 CharacterAction | 冲突胜负和被清空的硬成功字段 | Action 无 fact ID | 可追溯到 action/character，不到具体状态事实 | 无 | 无 | 不独立持久化；结果进入 action Event |
| Orchestrator | World/Event/Action/Patch | 实际 CharacterState、Event、旧 FactLedger 部分投影 | Event 有 ID；多数状态无 fact ID | `_apply_actions` 写状态时来源丢失；StatePatch 局部保留来源 | 当前快照覆盖旧值 | known_facts 只有字符串 | TickState、TickDB、FactLedger、MemoryStore |
| Narrator | 当前事件、角色状态、OpenLoop、记忆、reader facts、上一 continuity_state | 正文、continuity_state、events_consumed、OpenLoop 更新 | consumed Event/Loop 有 ID；continuity 字段无 fact ID | 正文可关联 tick/consumed events，continuity 子字段无来源 | 只有最新完整快照 | reader facts 与角色 known facts 分离 | narrative txt、sidecar、`tick_state.json` |
| NarrativeCritic | Narrator 草稿、场景、视点、风格约束 | 修订正文、trigger trace | 无事实 ID | 只保留原文/修改 trace，不建立事实证据链 | 无 | 无 | critic log/bench trace |
| NarrativeStateGuard | 前一 continuity、候选正文、声明后态、required events | 核验/修复正文、验证 trace | required Event 有 ID；ledger path/语言证据无稳定 fact ID | 主要靠 Event 描述、JSON path 和自然语言证据 | 前态/后态语义，没有事实有效区间 | 可检查知识越权但无统一 known_by | narrative sidecar/critic trace |
| TickState | World/Character/OpenLoop/reader/continuity/style | 当前运行时快照 | 实体/事件/loop 有 ID；状态事实无 ID | reader fact 有 event_id；其余字段多无来源 | 覆盖式当前快照 | known_facts 字符串、reader fact 列表 | `tick_state.json` |
| FactLedger | Orchestrator 的少量 action 推断 | location/death 等 append-only Fact | 有 Fact.id | 单个 source_event_id 字段，但当前常为空 | established_tick；没有 valid_until | 无 | `fact_ledger.json` |
| KnowledgeGraph | TickState 当前快照 | 实体属性与关系派生图 | 实体 ID；边无 fact ID | 不保存源 Event/Fact | 当前派生视图，无有效期 | 无 | `knowledge_graph.json`、snapshots |
| SummaryTree | legacy section 摘要、MemoryCompressor legendize | L0/L1/L2 摘要、L3 legend | node/legend 有 ID，不是 fact ID | child/original node IDs；不引用事实 | chapter range，不是事实有效期 | 无；legend 允许失真 | `summary_tree.json` |
| MemoryCompressor | MemoryEntry、OpenLoop origin event IDs | L1/L2 MemoryEntry、L3 legend | memory/source ID | source_ids 可回指 memory；不是事实来源链 | tick_range | 无 | MemoryStore、SummaryTree |
| ConsistencyGuardian | WorldState、CharacterState、事件、近期摘要 | 语义 conflict 与 hallucination flag | conflict 运行时 ID | evidence 是文本；不引用事实 ID | 无 | 依赖 LLM 推断 | 运行 trace/bench |
| SectionEditor | 多段正文、protected terms、style contract | 接缝编辑正文、验证/修复 trace | 无事实 ID | 以原文文本为权威证据 | 无 | verifier 语义判断 | section/trace，非 Tick 核心账本 |

### 权威性与派生关系

当前真正改变模拟状态的入口是 WorldSimulator 的 WorldState、Orchestrator 接受后的 CharacterAction、
StatePatch 和用户直接状态编辑；通过 StateGuard 后落盘的正文是读者可见结果。`TickState` 是当前状态快照，
但不是 append-only 来源账本。Event 是最稳定的因果锚点，却没有结构化 end-state。

以下结构目前是派生视图，不应各自创造冲突事实：旧 FactLedger、KnowledgeGraph、SummaryTree、
CharacterState.known_facts、continuity_state、reader knowledge、Narrator prompt context。当前代码尚未执行这一边界：
这些视图由不同写入点独立生成，只有少数位置保留 Event ID。

同一事实可能同时出现在 CharacterState、action Event、FactLedger、continuity_state、KnowledgeGraph、
MemoryEntry/SummaryTree 和正文中。高风险覆盖包括：

- `current_location`、inventory、status_effects 和 relationship 在 TickState 中覆盖旧值，却不记录旧事实为何失效。
- FactLedger 用 `(subject, kind)` 单指针；多个物品、状态、关系会互相抢占 active 槽位。
- `_ingest_facts_from_actions` 以 `action.target` 推断位置，而实际状态写入使用 `new_location`。
- `newly_learned` 直接追加字符串，无法证明来自哪个 visible Event；`newly_speculated` 没有持久 belief 类型。
- continuity_state 是 Narrator 声明的完整后态，但字段没有 source/fact ID，可能与 TickState 并行漂移。
- KnowledgeGraph 每 Tick 从当前快照覆盖派生关系，无法区分新事实、合法替代与数据丢失。
- SummaryTree/MemoryCompressor 保存历史叙述；L3 明确允许失真，不能恢复成当前状态或角色已知事实。
- OpenLoop 的 origin_event_ids/evidence_event_ids 尚未升级为 origin/resolution fact IDs。

### 当前上下文、复验、记忆、风格与测量

1. Narrator 已消费最近正文、事件、角色状态/known_facts、OpenLoop、reader knowledge、相关 PriorityMemory、
   风格快照和上一 continuity_state；Tick 主路径没有把 SummaryTree 作为明确 L2/L3 输入。
2. 正文依次经过 bounded Critic 和 NarrativeStateGuard；后者最多两次修复并再次验证。周期 Guardian 主要比较
   World/Character 快照、事件和近期摘要，不使用统一事实身份。
3. PriorityMemoryStore 有 L0-L2 条目与保护/检索；MemoryCompressor 以 50/500/5000 Tick 压缩并调用
   SummaryTree legendize，但 MemoryEntry ID 被当作 SummaryTree node ID 代理，主 Tick 的 section leaf 消费链不完整。
4. 风格 key/version/snapshot/prompt_hash 随小说持久化，旧作品优先读取 snapshot。Theme 与 style 注册表分离。
5. benchmark 已有逐 Agent Token/时延、StateGuard/critic trace、D1-D8、known-contract judge、匿名全候选分类、
   checkpoint/resume；盲区是跨视图事实对账、事实来源/有效期/known_by、SummaryTree 实际注入选择、
   以及 StateGuard 错误放行率的稳定 fact-level 统计。

## 三个优先假设

1. **P0-A：只读 CanonicalFact sidecar。** 从已接受的状态转换、Event/StatePatch、通过验证的正文后态、
   known facts 和 OpenLoop resolution 投影带稳定 ID 的事实，可在不改变生成行为的情况下识别来源缺失、
   supersede 和派生视图冲突。
2. **P0-B：StateGuard 只读事实前态。** 如果 P0-A 双轨对账稳定，把紧凑的 active fact expectations 提供给
   StateGuard、保留全部旧 fallback，可减少语言同义表达造成的错误修复，而不降低硬事实标准。
3. **P1：预算化 NarrativeContextBundle。** 如果 P0-B 稳定，按实体、OpenLoop、因果、时间与不可逆性选择
   SummaryTree L2/L3 和 CanonicalFact，可降低重播/历史状态恢复，而不会引发 Prompt/Token 或 D7 cascade。

P2 风格改动只有在 P0/P1 通过同输入 4-Tick 对照后才考虑；不会先修改 StylePreset。

## 分阶段实施与 Gate

1. Iteration 07：定义 CanonicalFact/Store、稳定 ID、状态机、原子 sidecar；先写至少 10 个事实链最小反例。
2. Iteration 08：从确定性状态变化/Event/StatePatch/continuity/known/OpenLoop 建立只读投影；旧结构继续工作。
3. Iteration 09：增加 CanonicalFact 对 TickState、旧 FactLedger、KG、continuity 的只读 reconciliation 报告。
4. Gate A 后，以完全未改变生成行为的版本运行同一 4-Tick baseline，确认 sidecar 零行为影响。
5. Iteration 10：仅当双轨稳定，StateGuard 只读消费紧凑 fact expectations，保留旧输入和 fallback。
6. 连续两次同输入 Gate B；目标 retained >= 8/12，硬错误/未兑现事件不增加，否则回滚或 INCONCLUSIVE。
7. Iteration 11：仅当 Gate B 稳定，构建有预算、理由 trace 的 NarrativeContextBundle。
8. Iteration 12：接入 SummaryTree L2/L3，明确历史/legend 低权威，重跑 Gate B 与小规模盲测。
9. Iteration 13–14：只在证据支持时做单一压力风格假设；不以关键词、固定句或删事件取巧。
10. Gate B 稳定后才运行 3 themes × 3 seeds × 30 ticks。Gate C 未通过则不运行 200 Tick；本阶段默认不运行 500 Tick。

## 通用接受与回滚条件

- 接受：相关/新增/全后端测试通过；旧数据可读；无 migration；sidecar 不改变生成；双轨严重冲突为零或可解释；
  三 seed 后无系统性退化；最差 seed 不显著恶化；Token 增量与收益相称。
- 回滚：硬事实错误增加；错误事实被 StateGuard 放行；sidecar 与旧结构出现大量不可解释双写；历史摘要覆盖当前事实；
  4-Tick <= 6/12 且成本上升；只改善一个 seed/theme；两次运行方向相反；通过降低阈值或删样本制造提升。

## 可复现命令

```powershell
python -m pytest backend/tests/ -v
Push-Location frontend
npm run build
Pop-Location
python scripts/bench_tick.py --help
python scripts/validate_styles.py --help
python scripts/classify_styles_blind.py --help
python scripts/analyze_longrange_drift.py --help
```

