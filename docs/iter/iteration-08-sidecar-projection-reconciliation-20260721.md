# Iteration 08 — sidecar projection and read-only reconciliation

- iteration_id: `20260721-08-sidecar-projection-reconciliation`
- date: `2026-07-21`
- base_git_sha: `dcbd255`
- candidate_git_sha: `d37a1c8`
- provider: not invoked for candidate validation
- model: not invoked for candidate validation; `glm-5.2` quota probe only
- temperature: not applicable
- themes: deterministic fixtures only
- styles: no style change
- seeds: deterministic fixtures only
- tick_count: mock full-chain 1 Tick; real-model 0 Tick

## Hypothesis

```text
Iteration: 08
Observation: CanonicalFact 基础模型存在，但没有从生产 Tick 合法写入点生成记录，也无法量化旧视图差异。
Root-cause hypothesis: 只有把投影放在已接受状态转换之后、Tick 持久化之前，并把对账做成只读工具，才能在不改变生成的情况下建立证据。
Single primary change: 接入 Event/World/Character/StatePatch/guarded continuity/OpenLoop resolution 的延迟 sidecar 投影；新增只读四视图对账器。
Files to change: canonical projection/reconciliation、Orchestrator/TickRuntime sidecar wiring、CLI 与测试。
Expected improvement: 每个已投影事实带来源/有效期/known_by；差异与 coverage gap 分开；投影失败不影响 Tick。
Possible regressions: sidecar 在失败 Tick 提前写入、投影改变正文、StatePatch 来源丢失、belief 被当 objective、额外 Token/LLM 调用。
Validation: 相关 64 项、全后端、前端 build、glm quota probe；真实 4-Tick 在费用 Gate 前暂停。
Rollback condition: 生产 Prompt/正文变化、sidecar 失败中断 Tick、旧数据需要 migration、belief/rumor 覆盖 objective、Gate A 回归。
```

## Result

- files_changed:
  - `backend/narrative/canonical_projection.py`: 只从 typed contract/accepted state diff 投影，不解析 consequences 自然语言。
  - `backend/narrative/canonical_reconciliation.py`: TickState、FactLedger、KG、continuity 只读对账。
  - `backend/narrative/canonical_facts.py`: 不变事实只合并来源，不制造假 supersede；更严格的 current load 校验。
  - `backend/agents/orchestrator.py`: 投影延迟到持久化边界；所有 sidecar 错误非致命。
  - `backend/tick_runtime.py`: sidecar load/save 生命周期。
  - `scripts/reconcile_canonical_facts.py`: 可复现的只读对账 CLI，冲突时 exit 1。
  - `backend/tests/test_canonical_projection.py`
  - `backend/tests/test_canonical_reconciliation.py`
  - `backend/tests/test_canonical_facts.py`
  - `backend/tests/test_orchestrator_p0.py`
- tests_added:
  - 投影/对账新增 13 个专项用例；Iteration 07 测试增加 1 个不变状态重复投影用例。
  - mock 生产全链路验证 `canonical_facts.json` 确实落盘，knowledge 来源和 known_by 存在。
- baseline_metrics:
  - production sidecar projection: absent
  - deterministic reconciliation: absent
  - backend: 1224 passed
- candidate_metrics:
  - focused regression: 64/64 passed
  - full backend: 1253 passed, 1 个既有 warning
  - frontend: PASS，55 modules，JS 320.55 kB / gzip 95.20 kB
  - new LLM calls per Tick: 0
  - new prompt tokens per Tick: 0
  - quota probe: `glm-5.2` healthy；只进行 1 个最多 80 output-token 的探测调用
- fact_errors: deterministic fixtures 0；真实模型尚未跑，不能声明生成质量改善
- style_results: 未测；没有修改 StylePreset、style prompt 或 judge
- cost:
  - deterministic validation: 0 model tokens
  - runtime sidecar: 本地 JSON/hash/diff I/O；未增加 LLM 调用
  - 预计同一 3 styles × 4 Tick：约 13–22 万 Token，历史墙钟 2,213 秒
  - 预计 7 styles × 4 Tick × 2 runs：约 55–85 万 Token，另加 blind judge
- decision: `ACCEPT`（基础/测量能力）；生成质量结论仍 `INCONCLUSIVE`
- rollback_status: not required

## Projection authority and safeguards

- World/Character/StatePatch 使用实际 before/after state，不采用 action 文案猜测。
- Event 只保存 `event_occurred` 历史记录；不把 free-form consequences 解析成客观事实。
- `newly_speculated` 明确保存为 `belief`，不进入 objective-current。
- continuity 只读取 documented characters/items/knowledge 字段；缺字段不产生恢复/痊愈。
- guarded continuity 与状态不同会形成可对账差异，不会静默改回旧 TickState。
- sidecar 写入延迟到 Tick 已完成叙述与维护之后；异常只 warning，不改变生产结果。

## Benchmark gate

真实 4-Tick 尚未执行。理由不是 provider 不可用：quota probe 已成功；理由是附件明确要求预计显著费用时先停止并给出估算。上一轮同一三风格序列从 `started_at=1784570456` 到
`finished_at=1784572669`，耗时 2,213 秒。需用户确认费用后才能继续 Gate B。

## Verification

```powershell
python -m pytest backend/tests/test_canonical_facts.py `
  backend/tests/test_canonical_projection.py `
  backend/tests/test_canonical_reconciliation.py `
  backend/tests/test_orchestrator_p0.py `
  backend/tests/test_orchestrator_state_transitions.py `
  backend/tests/test_state_patch.py `
  backend/tests/test_event_injector_state_patch.py -q
python -m pytest backend/tests/ -q
Push-Location frontend
npm run build
Pop-Location
python scripts/reconcile_canonical_facts.py --help
```

