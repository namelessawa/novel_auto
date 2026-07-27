# Writer Planning Mode 验收报告

## 结论

`WRITER_PLANNING_FAIL`

ChapterPlan、Planner 隔离、事务保护和新增指标均已实现，真实 Mini 中计划本身
`15/15` 通过确定性校验，且无 Provider、硬事实、状态或事务错误。但是 Writer
首次正文直接通过仅 `2/15`，Retry `13/15`，Repair 依赖 `8/15`，未达到本阶段
“提高第一次生成质量、减少 Retry/Repair”的核心 Gate。

因此不允许执行，也未执行 Stage1 Full Matrix（3 themes × 5 styles × 3 sections）。

## 基线与边界

| 项目 | 值 |
| --- | --- |
| base branch | `codex/writer-first-pass-optimization-20260727` |
| base commit | `6f303cfa55e45bb1932b23b8fc6cb5eaf6b69c14` |
| working branch | `codex/writer-planning-mode-20260727` |
| real provider model | `glm-5.2` |
| real matrix seed | `20260727` |
| desired length | `900`（硬接受区间 900–1100） |
| real run time | 2026-07-27 10:58:26–11:23:52（Asia/Shanghai） |

未修改 StoryBible、CanonicalState、NarrativeContract 或事实 Validator；未增加
Critic、第二生成 Agent、无限 Retry 或 LLM Judge。上一阶段
`TransactionRevisionGuard` 保持生效。

## 1. ChapterPlan 设计

新增：

- `backend/story/chapter_plan.py`
- `backend/story/chapter_plan_validator.py`

`ChapterPlan` 是一次性、节内、非权威的 Writer 计划，包含：

- `section_id` 与唯一 `target_chars`；
- 固定顺序的 opening / development / conflict / resolution 四段；
- 每段目标字符数及绑定的既有事件 ID；
- 冻结的 required event ID、required end-state ID；
- 来自 `SectionBudgetPlan` 的 stop conditions。

模型使用 `extra="forbid"` 的闭合 Schema，不能携带 `state_delta`、StoryThread
变更或 memory。Planner 仅能复制并分配现有 ID，不能借自由文本添加人物、地点、
物品、组织、背景或世界规则。

确定性计划校验覆盖：

- 所有 required event 至少绑定一段，缺失报 `PLAN_EVENT_MISSING`；
- 事件不能新增、重复或改变执行顺序；
- required end states 必须完整保留且存在 resolution 段，缺失报
  `PLAN_END_STATE_MISSING`；
- 四段字符预算之和必须严格等于 `target_chars`；
- section、target、结构与 stop conditions 必须匹配冻结权威；
- 未授权人物、地点、物品、组织引用拒绝。

计划校验失败时事务记录为 `CHAPTER_PLAN_INVALID`，正文 Writer 不被调用，也不能
进入 stage/commit。

## 2. Planner 流程

默认 `AuthorWriter.plan()` 通过一次真实 LLM 调用生成 ChapterPlan。输入严格收敛为：

1. StoryBible；
2. CanonicalState；
3. NarrativeContract；
4. EventExecutionPlan；
5. SectionBudgetPlan；
6. StyleBalanceContract。

Planner prompt 明确其不是 Agent、Canon、Memory 或 State，只负责篇幅和既有事件/
终态分配。温度为 0，输出上限 2048 token，采用 ChapterPlan JSON Schema。

运行顺序已改为：

```text
Context
  -> Writer Planner
  -> ChapterPlan Validator
  -> Writer
  -> WriterPreflight
  -> Full Validator
  -> one-shot Repair Patch
  -> Commit
```

测试注入的旧式 deterministic Writer 使用同一冻结权威生成的安全 fallback plan，
不产生 Provider 调用；真实默认 Writer 始终走 LLM Planner。

## 3. Writer 变化

Writer 最终执行令现在逐段列出：

- Segment order；
- purpose；
- target chars；
- assigned event IDs；
- required end states；
- stop conditions；
- “完成第四段后停止”。

同时明确：

> 不要创造新的剧情来填充长度；长度来自已有事件展开，而不是新人物、新背景或新冲突。

`WriterCandidate` 新增 `chapter_evidence`，每个 segment 只报告
`events_completed`。该证据只用于诊断，不覆盖正文 Validator。

指标定义：

- `chapter_plan_success_rate`：ChapterPlan 通过确定性冻结权威校验；
- `writer_plan_follow_rate`：chapter evidence 完整，且初稿正文 Preflight 的长度、
  四段结构、事件覆盖和终态同时通过；
- `first_pass_after_plan_rate`：有效计划之后初稿通过 Preflight 和完整 Validator；
- `writer_first_pass_rate`：保持上一阶段口径。

真实 Mini 中 evidence-only mapping 为 `15/15`，但严格正文 follow 只有 `2/15`。
这一区分避免把 Writer 自报 evidence 误当成计划执行成功。

## 4. 风格约束

Style 仍只控制表达，不控制事件数量、章节结构或长度：

- `warm_healing`：每个温暖段落必须推动既有事件，不能只增加情绪；
- `noir_cold`：短句不等于短章节，每个必要事件必须具备行动、决定、结果；
- `hot_blooded`：强度只来自既有事件，禁止新增敌人、战争、伤亡、受伤；
- `classical_chapter`：古典感只来自语言、句法、节奏，禁止新增历史背景。

## 5. 自动化与离线结果

| 验证 | 结果 |
| --- | --- |
| ChapterPlan / Validator / Planning Mode 新增测试 | 16/16 |
| 后端全量测试 | 1551 passed；1 条既有 Starlette deprecation warning |
| 24 个历史失败案例 | 24/24；Repair 17/17；regression 0；bad commit 0 |
| Stage1 六个失败案例 | 6/6；patch failure 0；validator failure 0；regression 0 |
| Author UI | 14/14 |
| 前端生产构建 | passed |
| Python compile / `git diff --check` | passed |

事务安全专项覆盖：

- planner 不改变 CanonicalState、StoryThread、Memory 或 journal revision；
- plan failure 不能生成正文或提交；
- Writer failure 不能提交；
- revision mismatch、recovery mismatch、revision jump 仍由
  TransactionRevisionGuard 拒绝。

离线 artifact（本地 `.tmp`，不纳入 Git）：

| Artifact | SHA-256 |
| --- | --- |
| `.tmp/writer-planning-mode/offline-24.json` | `b2f77be1d37c5fd52f860e5ef4678df807bd2c3d50a96d81276f928ca2e38159` |
| `.tmp/writer-planning-mode/offline-six.json` | `871dc3f50003f8938c8f1726c8afe437f4246237c04fb94fc6992aa0291ec81b` |

## 6. 15 节真实 Mini Matrix

配置：

```text
theme=action_conflict
styles=literary,noir_cold,warm_healing,hot_blooded,classical_chapter
sections_per_style=3
model=glm-5.2
desired_length=900
seed=20260727
provider=custom（coding.txt）
```

| 风格 | 提交 | Plan | 初稿直通 | Retry | Repair | 900–1100 | 平均长度 | Token | 平均延迟 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| literary | 3/3 | 3/3 | 1/3 | 2/3 | 1/3 | 3/3 | 920.33 | 58,662 | 67.81s |
| noir_cold | 2/3 | 3/3 | 0/3 | 3/3 | 3/3 | 2/3 | 935.33 | 82,992 | 105.88s |
| warm_healing | 3/3 | 3/3 | 0/3 | 3/3 | 3/3 | 3/3 | 960.33 | 83,781 | 93.73s |
| hot_blooded | 3/3 | 3/3 | 1/3 | 2/3 | 0/3 | 3/3 | 979.33 | 56,828 | 71.86s |
| classical_chapter | 3/3 | 3/3 | 0/3 | 3/3 | 1/3 | 3/3 | 956.67 | 72,550 | 168.13s |
| **合计** | **14/15** | **15/15** | **2/15** | **13/15** | **8/15** | **14/15** | **950.40** | **354,813** | **101.48s** |

Planner 确实稳定生成了合法结构，但正文第一次执行仍不稳定：

- 初稿过短 9 次；
- 初稿过长 4 次；
- 初稿必要事件覆盖不足 4 次；
- Retry 后仍过短 5 次；
- Retry 后事件覆盖不足 4 次；
- Retry 后终态不可达 2 次。

完整 narrative validation 历史问题：

- `NARRATIVE_TOO_SHORT` 6 次；
- `REQUIRED_EVENT_MISSING` 4 次；
- `END_STATE_WRONG_HOLDER` 2 次；
- `POST_RESOLUTION_EXPANSION` 1 次；
- `REQUIRED_EVENT_INCOMPLETE` 1 次。

唯一拒绝发生在 noir_cold：Repair 后正文为 893 字，事件和终态已完成，但仍低于
900 字下限。该候选被拒绝，没有提交。

## 7. First pass、Retry 与 Repair

| 指标 | Gate | 实际 | 结果 |
| --- | ---: | ---: | --- |
| 初稿直接通过 | ≥8/15 | 2/15（13.33%） | FAIL |
| writer plan follow | 诊断指标 | 2/15（13.33%） | — |
| first pass after plan | 诊断指标 | 2/15（13.33%） | — |
| Retry | 越低越好 | 13/15（86.67%） | — |
| Repair dependency | ≤40% | 8/15（53.33%） | FAIL |
| Repair success | ≥90% | 7/8（87.50%） | FAIL |

计划阶段解决了“计划是否合法”的问题，但没有解决 `glm-5.2` 在正文中精确遵守
字符预算和单事件完成证据的问题。因此本阶段不能声称 Writer first pass 获得改善。

## 8. Token、Latency 与 Provider

| 项目 | 实际 |
| --- | ---: |
| Prompt token | 299,087 |
| Completion token | 55,726 |
| Total token | 354,813 |
| Planner token（Total 子集） | 49,646 |
| Retry token（Total 子集） | 138,947 |
| Repair token（Total 子集） | 37,028 |
| Provider calls | 51 |
| Planner calls | 15 |
| Writer initial calls | 15 |
| Retry calls | 13 |
| Repair calls | 8 |
| 平均端到端延迟 | 101.4831s/节 |
| Provider error | 0 |

调用恒等式：

```text
51 = 15 Planner + 15 initial + 13 Retry + 8 Repair
```

真实矩阵 artifact：

| Artifact | SHA-256 |
| --- | --- |
| `.tmp/writer-planning-mode/real-mini/stage1-matrix.json` | `36fba8ad5d87703f5a5a4a1b66fb6c93c4e6414fe77a604c9331decf70cafdaf` |
| `.tmp/writer-planning-mode/real-mini/stage1-matrix.md` | `bafff2a2a40e0f2ec35831b5cdd5c23f97c2f0fbc607d2461a328b2146a9d714` |

## 9. Gate 与 Stage1 决策

| Gate | 要求 | 实际 | 结果 |
| --- | ---: | ---: | --- |
| 正式提交 | ≥14/15 | 14/15 | PASS |
| 初稿直接通过 | ≥8/15 | 2/15 | FAIL |
| Contract | ≥93% | 14/15（93.33%） | PASS |
| Repair success | ≥90% | 7/8（87.50%） | FAIL |
| Repair dependency | ≤40% | 8/15（53.33%） | FAIL |
| 长度 900–1100 | ≥93% | 14/15（93.33%） | PASS |
| ChapterPlan success | ≥95% | 15/15（100%） | PASS |
| 硬事实错误提交 | 0 | 0 | PASS |
| 状态冲突提交 | 0 | 0 | PASS |
| 事务损坏 | 0 | 0 | PASS |
| Provider error | 0 | 0 | PASS |

最终 Gate：`MINI_MATRIX_FAIL`。

Stage1 Full Matrix：**不允许，不执行**。

## 10. 证据边界

| 边界 | 本阶段含义 |
| --- | --- |
| deterministic | ChapterPlan Validator、Preflight、Narrative/Event/EndState/Length/Ending/State Validator、Revision Guard、Gate 与自动化测试 |
| recorded | 24/24 与 6/6 frozen fixture；不是本次 Provider 文学样本 |
| real provider | 15 节由 `glm-5.2` 真实执行；Token、Latency、调用、错误与正文保存在本地矩阵 |
| human review | 未执行；不声明人工文学质量验收 |
| LLM judge | 未执行；所有 PASS/FAIL 均来自确定性规则和数值 Gate |

本报告不把合法 ChapterPlan、Writer 自报 evidence 或最终 Repair 成功等同于 Writer
首次生成质量通过。
