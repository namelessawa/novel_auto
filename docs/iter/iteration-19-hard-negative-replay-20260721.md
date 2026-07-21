# Iteration 19 — complete signal-backed hard-negative replay

- iteration_id: `20260721-19-hard-negative-replay`
- date: `2026-07-21`
- base_git_sha: `9f23ce4`
- candidate_git_sha: `23a6189`

```text
Iteration: 19
Evidence gap:
Phase 8 has zero decisive rejects with actual StateGuard signals. Synthetic labels
exist, but they never traverse verifier/repair/reverify in the production runtime.

Hypothesis:
A versioned suite of at least 12 complete synthetic negatives can establish the
first measurable hard-negative baseline without changing production decisions.

Single primary change:
Extend the existing full-runtime replay with a case-suite schema and add 12 complete
hard negatives, each with Narrator, verifier and repair payloads.

Behavior changed:
No production Guard behavior. One fixture-only opt-in forces the existing Critic so
its production component and trace capture are measured under pytest.

Expected metric:
At least 12/12 expected rejects remain rejected; every attempted repair retains full
prose; at least six hard-negative categories and one Critic path are covered.

Safety risk:
Synthetic verifier responses could bypass the actual Guard, a repair payload could
be missing, location/holder hard errors could be accepted, or fixture tokens could
be mislabeled provider usage.

Cost:
0 provider calls; fixture tokens N/A.

Validation:
Deterministic fixture builder, category counts, actual TickRuntime/Orchestrator path,
three verifier and two repair rounds per case, Critic trace, focused and full tests.

Rollback condition:
Any hard negative accepted, incomplete trace, fewer than 12 signal-backed rejects,
production decision change, provider call or backend regression.
```

## Result

- Tests: 40 focused passed; full backend `1299 passed, 1 existing warning`.
- Dataset coverage: Phase 8 base remains 73; the separate Phase 9 suite adds 12
  decisive synthetic negatives. They are not yet presented as human gold labels.
- Signal-backed accepts/rejects: carried accepts 20 / new rejects 12.
- Independent reviews: 0.
- Typed candidate coverage: not calculated until Iteration 22.
- Precision/recall/FPR/FNR/abstain: not calculated; no typed candidate exists.
- Hard errors allowed: 0/12.
- Probable false positives reduced: 0; behavior unchanged.
- Cost: 121 fixture transport calls, 0 provider calls, model tokens N/A.
- Decision: `ACCEPT_MEASUREMENT`.
- Rollback: not required.

Suite evidence:

- fixture: `backend/tests/fixtures/runtime_replay/phase9_hard_negative_suite_v1.json`
- report: `docs/iter/phase9-hard-negative-replay-20260721.json`
- expected/actual rejects: 12 / 12
- complete traces: 12 / 12
- verifier rounds: 36 complete
- repair rounds: 24 complete; every round contains full prose and state
- Critic exercised: 1 case; complete input/output retained
- all eight completeness flags: 12 / 12
- provider calls: 0
- model tokens: N/A
- stable suite evidence SHA-256:
  `3f30f1626356d6e9197f89d0caf901f934dced9433ce882aca2c3fbc2fd9b6b8`

At least three decisive fixtures cover each of endpoint, location, holder,
condition, knowledge leak, ungrounded fact, ledger wrong type, ledger missing field
and repair fact change. These are synthetic signal-backed regression fixtures, not
real-model or independently reviewed novel-quality evidence.
