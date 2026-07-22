# Event Completion Repair 验收报告（2026-07-22）

## 1. 最终结论

`EVENT_REPAIR_FAIL`

Stage 0 离线门通过，但最终一次独立真实 15 节小矩阵仅提交 9/15，未达到
`>=14/15`、Contract `>=93%`、Repair 成功率 `>=90%`。因此严格停止于 M7；
完整 45 节 Stage 1 以及 Stage 2/3/4 均未运行。

## 2. 基线与分支

- 工作分支：`codex/event-completion-repair-20260722`
- 最新 Narrative Contract / Stage 1 基线分支：`codex/narrative-contract-longrun-20260722`
- 基线 SHA：`2fa3c9e44b28f927b21dac62a8847220be4c70d3`
- 更早的用户指定工作基础：`codex/author-memory-refactor-20260721` @ `00cc9256c16ab5b705d32ba1c46f28a37152812e`
- 最终 SHA：由提交后的最终交接记录提供（提交无法在自身内容中稳定记录自身 SHA）

相对基线的主要变化：确定性 EventExecutionPlan、逐事件完成/终态验证、Writer 证据提示、
确定性 RepairPlan、prose-only Repair、原始 delta/thread 重新验证与剔除、RepairRegression、
Author Studio 事件/终态/Repair 展示、24 案例 fixture/replay、真实矩阵与长程 runner 门禁。

## 3. 架构结果

正式链路为：

```text
NarrativeContract
→ deterministic EventExecutionPlan
→ Writer（event/end-state evidence 仅作定位提示）
→ EventCompletion + EndState + Narrative Validator
→ deterministic RepairPlan
→ 最多一次 prose-only LLM Repair
→ 仅删除 Validator 已证明的 UNSUPPORTED_* 子句（若存在）
→ 全量 Narrative/Event/EndState/RepairRegression 复验
→ 用修复后正文重新验证原始 StateDelta / StoryThread proposals
→ 剔除无证据提案
→ journaled commit
```

确定性清理没有第二次 LLM 调用，也没有修改事件、终态、事实、长度或结构化提案的权限；
清理造成任何必要事件/终态/保留事实回归时，事务仍被拒绝。

## 4. 里程碑

| 里程碑 | 结果 | 测试/失败 | Provider 与 token | 下一 Gate |
|---|---|---|---:|---|
| M0 基线与样本 | 完成 | 定位 45 次原始矩阵与 24 个拒绝 | 0 | 允许 M1 |
| M1 EventExecutionPlan | 完成 | 有序事件、actor/action/target、完成测试、终态 | 0 | 允许 M2 |
| M2 completion validator | 完成 | missing/mentioned/started/attempted/completed/contradicted、wrong actor/target、持有人最终态 | 0 | 允许 M3 |
| M3 RepairPlan | 完成 | 缺失/未完成/错 actor/target/终态、删除项、长度、preserve | 0 | 允许 M4 |
| M4 prose-only 与双层复验 | 完成 | 非正文 Repair 字段忽略并记录；delta/thread 重新证明 | 0 | 允许 M5 |
| M5 前端 | 完成 | Author UI 14/14 | 0 | 允许 M6 |
| M6 24 案例回放 | PASS | 24/24；0 regression；0 bad commit | recorded/deterministic，0 real token | 允许 M7 |
| M7 真实小矩阵 | FAIL | 最终独立矩阵 9/15；Repair 3/9 | 24 calls，105,546 tokens | 禁止 M8 |
| M8 Stage 1（45） | NOT_RUN | M7 Gate 未通过 | 0 | 禁止 |
| M9 Stage 2（120） | NOT_RUN | Stage 1 未通过 | 0 | 禁止 |
| M10 Stage 3（300） | NOT_RUN | Stage 2 未运行 | 0 | 禁止 |
| M11 Stage 4（200–300） | NOT_RUN | Stage 3 未运行 | 0 | 禁止 |
| M12 审查与报告 | 完成 | 全回归、构建、diff 与凭据边界检查 | 0 | 提交分支 |

开发期间共执行四次新的真实 15 节诊断矩阵，均未达到 Gate；合计 60 次真实尝试、
96 次 Writer/Repair 调用、419,639 tokens。它们用于暴露并修复确定性误判与 Repair
不服从问题，不合并计数，也不替代最终独立矩阵。

## 5. 24 个冻结失败案例

fixture：`backend/tests/fixtures/stage1_event_repair_failures.json`，24 个原文 SHA-256
固定，无密钥、URL、绝对路径或无关日志。

原始预期违规汇总：

| code | 数量 |
|---|---:|
| `REQUIRED_EVENT_MISSING` | 15 |
| `END_STATE_NOT_REACHED` | 10 |
| `DELTA_NARRATIVE_MISMATCH` | 5 |
| `THREAD_FIELD_OVERRIDE_FORBIDDEN` | 4 |
| `THREAD_ADVANCE_UNKNOWN` | 2 |
| `THREAD_ADVANCE_NO_EVIDENCE` | 1 |
| `NARRATIVE_TOO_LONG` | 1 |

最终离线回放：

- 24/24 最终 Contract accepted；其中 7 个由新确定性验证直接恢复，17 个执行一次 recorded Repair。
- RepairPlan 合计：missing event 8、incomplete event 5、wrong end state 6。
- 17/17 Repair 成功，RepairRegression 0，坏提交 0。
- 剔除 26 条无证据 delta、10 条非法/无证据 thread change；最终错误 delta/thread 提交 0。
- 证据级别仅为 deterministic + recorded，不代表真实 provider 成功率。

## 6. 最终真实 15 节小矩阵

输出目录：`.tmp/event-completion-repair/mini-matrix-r4-20260722`（本地证据，不提交）。

| 指标 | 实际 | Gate |
|---|---:|---:|
| 组合 | 5/5 | 5/5 |
| 真实尝试 | 15/15 | 15/15 |
| 正式提交 | 9/15 | >=14/15 |
| Contract pass | 9/15 = 60.00% | >=93% |
| Repair | 9/15 = 60.00% | 观察项 |
| Repair success | 3/9 = 33.33% | >=90% |
| 硬拒绝 | 6 | 允许但不可计入提交 |
| prompt tokens | 85,996 | 记录 |
| completion tokens | 19,550 | 记录 |
| repair tokens（completion 子集） | 16,656 | 记录 |
| total tokens | 105,546 | 记录 |
| 平均 latency | 27.097 秒 | 记录 |
| Provider errors | 0 | 0 |

按风格：literary 1/3、noir_cold 2/3、warm_healing 1/3、hot_blooded 2/3、
classical_chapter 3/3。最终拒绝码汇总：`REQUIRED_EVENT_MISSING` 5、
`REQUIRED_EVENT_INCOMPLETE` 3、`END_STATE_WRONG_HOLDER` 2、`NARRATIVE_TOO_SHORT` 1。

6 个拒绝中：3 个 Repair 原样返回；1 个补长后仍低于最小长度；2 个虽改写但仍未通过
确定性事件/持有人终态校验。该矩阵的 provider、硬事实错误提交、状态冲突提交、事务损坏
均为 0。Gate 结果：`MINI_MATRIX_FAIL`。

## 7. Stage 1 与长程阶段

- Stage 1（3 主题 × 5 风格 × 3 节）：`NOT_RUN`（M7 Gate 未通过）。
- Stage 2（120 节）：`NOT_RUN`。
- Stage 3（300 节）：`NOT_RUN`。
- Stage 4（200–300 节）：`NOT_RUN`。

## 8. 安全门

在最终真实小矩阵中：硬事实错误提交 0、状态冲突提交 0、事务数据损坏 0、
Provider error 0、凭据泄露 0；各组合 integrity 列表为空。被拒绝事务没有进入正式章节，
revision 只随 committed transaction 推进。离线回放中无证据 StateDelta 和非法
ThreadChange 最终提交均为 0。

Stage 1/2/3/4 未执行，因此不对这些阶段的半提交、重复章节、revision 跳号或恢复成功率
作超出证据范围的声明。

## 9. 证据边界

- deterministic：服务端计划、验证、提案剔除、回归保护、测试与统计。
- recorded：24 案例中的固定 Repair 响应；只证明流程。
- real provider：最终 15 次小矩阵及前三次诊断矩阵；模型 `glm-5.2`。
- human review：未执行正式人工盲评；只做失败定位，不计为 Gate。
- LLM judge：未执行。

## 10. 验证命令

| 命令 | exit | 结果 |
|---|---:|---|
| 8 个聚焦测试文件 | 0 | 57 passed |
| `replay_stage1_event_failures.py` | 0 | 24/24，17/17 Repair，0 regression/bad commit |
| 最终 15 节真实矩阵 | 1 | 正常 Gate 失败：9/15，`MINI_MATRIX_FAIL` |
| `python -m pytest backend/tests/ -q` | 0 | 1469 passed，1 个 Starlette/httpx2 弃用 warning |
| 用户指定全 scripts Ruff 命令 | 1 | 14 个既有、非本分支脚本 lint 项 |
| 本次改动范围 Ruff 命令 | 0 | All checks passed |
| `python -m compileall -q ...` | 0 | passed |
| `npm run test:author` | 0 | 14 passed |
| `npm run build` | 0 | Vite build passed，59 modules |

结论保持 `EVENT_REPAIR_FAIL`：安全性继续成立，但真实 Provider 的一次 Repair 尚未稳定达到
可用率，不能执行或宣称 Stage 1 通过。
