# Iteration 07 — CanonicalFact sidecar foundation

- iteration_id: `20260721-07-canonical-fact-sidecar`
- date: `2026-07-21`
- base_git_sha: `8cb645be1f9713c085e5ef722ae91c55b75eed77`
- candidate_git_sha: `dcbd255`
- provider: not invoked
- model: not invoked
- temperature: not applicable
- themes: not applicable
- styles: not applicable
- seeds: not applicable
- tick_count: 0

## Hypothesis

```text
Iteration: 07
Observation: TickState、FactLedger、KG、SummaryTree、known_facts 和 continuity_state 没有共享事实身份、来源、有效期和 known_by。
Root-cause hypothesis: 缺少位于确定性状态转换与派生视图之间的 append-oriented 统一事实投影层。
Single primary change: 新增独立 CanonicalFact sidecar 模型、状态机、稳定 ID 与持久化；不接入 Prompt/Guard。
Files to change: backend/narrative/canonical_facts.py、backend/tests/test_canonical_facts.py、Phase 7 计划/状态。
Expected improvement: 最小事实链能确定性区分 active/superseded/historical/rumor/belief、来源和 known_by。
Possible regressions: 旧数据读取失败、错误 supersede、rumor 覆盖 objective、ID 不稳定、sidecar 要求 migration。
Validation: 15 个新反例、57 个旧账本/状态/摘要回归；不调用真实模型。
Rollback condition: 改变生成行为、旧状态不可读、无来源 active 事实通过、派生摘要覆盖当前事实或测试回归。
```

## Result

- files_changed:
  - `backend/narrative/canonical_facts.py`: versioned/atomic `canonical_facts.json`、稳定 fact ID、来源类型、
    objective-current 独立索引、supersede/invalidate、known_by/subjective 查询和幂等来源合并。
  - `backend/tests/test_canonical_facts.py`: 15 个确定性反例。
  - `docs/iter/PHASE7_PLAN.md`: 仓库审计、事实数据流表、优先假设和 Gate。
  - `docs/iter/PHASE7_STATUS.md`: 当前 Gate/迭代状态。
- tests_added: `backend/tests/test_canonical_facts.py`
- baseline_metrics:
  - unified fact ID/source/validity/known_by coverage: absent
  - minimum Phase 7 fact-chain regression cases: 0/10
- candidate_metrics:
  - new deterministic cases: 15/15 passed
  - legacy FactLedger/TickState/SummaryTree/quarantine/longrange cases: 57/57 passed
  - LLM calls/tokens/latency: 0 / 0 / not applicable
  - production consumers changed: 0
- fact_errors: none in deterministic fixtures
- style_results: not measured; no style or generation change
- cost: zero runtime cost because the sidecar has not been wired into TickRuntime
- decision: `ACCEPT`
- rollback_status: not required

## Safety properties demonstrated

1. 地图交付后旧 holder 被 supersede，不能继续作为 current。
2. 历史摘要的“完好地图”不能覆盖当前“雨损地图”。
3. `moving_to` 不会被查询成 `arrived`。
4. 后文省略伤势不会自动痊愈。
5. rumor/belief 不进入 objective-current 索引。
6. 角色谎言不能覆盖权威 item holder。
7. active 事实必须有权威来源；summary/legend/KG 不能创建 active。
8. stable ID 与输入来源顺序无关；同 ID 语义碰撞 fail loud。
9. 同一事实重放幂等合并来源和 known_by。
10. sidecar 原子保存，缺失 sidecar 对旧小说返回 False，不要求 migration。

## Limitations

- 本轮只证明数据结构和状态机正确，不证明生成质量改善。
- 尚未从 Event/StatePatch/TickState/continuity_state 自动投影。
- 尚未双轨对账，也未接入 StateGuard、Narrator 或 SummaryTree。
- 没有运行真实模型，因此 Gate B 仍未开始。

## Verification

```powershell
python -m pytest backend/tests/test_canonical_facts.py -q
python -m pytest backend/tests/test_fact_ledger.py `
  backend/tests/test_tick_state.py `
  backend/tests/test_summary_tree_persistence.py `
  backend/tests/test_state_quarantine.py `
  backend/tests/test_narrative_longrange_guards.py -q
```

