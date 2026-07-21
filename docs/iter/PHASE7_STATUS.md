# Phase 7 状态

更新时间：2026-07-21

## 当前阶段

- 状态：`IN PROGRESS — audit complete, Iteration 07 design`
- 行为基线：`6477f61b3ade9f3e984f66f457521976106edac9`
- 起始 HEAD：`8cb645be1f9713c085e5ef722ae91c55b75eed77`
- 当前结论：尚无质量提升结论；目前只有审计与 Gate A 基线证据。

## 已完成

- 读取上一轮最终/初始报告和 Iteration 02–06。
- 审计 Narrator、Critic、StateGuard、Guardian、Showrunner、MemoryCompressor、Orchestrator、
  TickState、FactLedger、SummaryTree、MemoryStore、KnowledgeGraph、SectionEditor 与测量脚本。
- 记录事实数据流、权威/派生边界、来源断点和三项优先假设，见 `PHASE7_PLAN.md`。
- 基线 Gate A：后端 `1224 passed, 1 warning`；前端 build PASS。
- 保留既有 4-Tick `6/12`、盲测 Top-1 `50%` / Top-3 `58.33%` 作为对照；没有将其重跑或描述成新结果。

## 当前迭代

```text
Iteration: 07
Observation: 多个事实视图没有共享稳定 ID、来源、有效期与 known_by；StateGuard 只能用语言/JSON path 猜测。
Root-cause hypothesis: 缺少位于确定性状态转换与各派生视图之间的 append-only 统一事实投影层。
Single primary change: 新增只读 CanonicalFact sidecar 模型、状态机、稳定身份与单元测试；不接入 Prompt/Guard。
Files to change: backend/narrative/ 新模块；backend/tests/ 新回归测试；本迭代记录。
Expected improvement: 10 个最小事实链案例可确定性区分 active/superseded/historical/rumor/belief 和来源缺失。
Possible regressions: 旧数据加载失败、稳定 ID 碰撞、错误 supersede、序列化不可逆、误把 rumor 当 objective。
Validation: 新测试、FactLedger/TickState 相关测试、全后端；此轮不运行真实模型。
Rollback condition: 改变生产生成、要求 migration、旧状态不可读、无来源事实被默认为权威、测试回归。
```

## Gate 状态

| Gate | 状态 | 证据/阻塞 |
| --- | --- | --- |
| A | baseline PASS | 1224 tests；frontend build PASS |
| B | 未开始 | 先完成 sidecar、投影、对账和零行为影响验证 |
| C | 禁止进入 | Gate B 尚未稳定通过 |
| D | 禁止进入 | Gate C 尚未通过，且未准备改生产默认 |
| E | 默认不运行 | 未获费用许可，也不满足前置 Gate |

## 敏感信息与工作树

- 不读取、不打印、不记录任何 API Key。
- provider 配置只记录变量名/存在性与非敏感 model/provider 元数据。
- `scripts/openai_compatible_chat.py` 是任务开始前出现的未跟踪文件，本任务不读取、不修改、不提交。
- 未 push、未创建 PR、未部署、未修改生产数据。

