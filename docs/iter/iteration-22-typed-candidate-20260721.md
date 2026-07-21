# Iteration 22 — offline typed candidate decision

- iteration_id: `20260721-22-typed-candidate`
- date: `2026-07-21`
- base_git_sha: `309b56c`
- candidate_git_sha: `d44d636`

```text
Iteration: 22
Evidence gap:
TypedContinuityState exists, but it has zero offline decision coverage and no
abstain-aware precision/recall/FPR/FNR comparison against complete Guard traces.

Hypothesis:
A production-disconnected candidate can combine required endpoints, authoritative
typed pre-state, declared typed end-state, prose and structured verifier checks to
resolve most complete cases while abstaining on invalid typed payloads.

Single primary change:
Add an offline-only typed candidate and a coverage-aware evaluator with Wilson 95%
intervals and baseline-preserving fallback metrics.

Behavior changed:
None. Narrator, NarrativeStateGuard and Orchestrator do not import the candidate.
No feature flag or production decision path was added.

Expected metric:
Coverage >=70%, abstain <=30%, no accepted hard negative, all repair fact changes
rejected and the captured synonym false reject resolved offline.

Safety risk:
Conditional metrics could hide hard negatives behind abstention; verifier summaries
could override typed/prose evidence; fixture expected labels could leak into the
candidate; offline results could be misreported as a production improvement.

Cost:
0 provider calls; 0 model tokens; deterministic local evaluation only.

Validation:
Complete 25-case replay evaluation, explicit invalid-ledger abstentions, no hard
negative accepts, no production imports, Wilson intervals and baseline-fallback
confusion matrix.

Rollback condition:
Any hard negative accepted, coverage below 70%, abstain above 30%, repair fact
change accepted, production import or CanonicalFact use.
```

## Result

- Tests: 15 focused Phase 9 tests passed; final backend/build validation follows.
- Dataset coverage: 98 total, 59 decisive, 39 ambiguous (39.8%).
- Signal-backed accepts/rejects: 33 / 12.
- Independent reviews: 0.
- Typed candidate coverage: 22/25 = 88.0%, Wilson 95%
  `[0.700442, 0.958332]`.
- Typed candidate abstain: 3/25 = 12.0%, Wilson 95%
  `[0.041668, 0.299558]`.
- Covered-case precision/recall/FPR/FNR: 1.000 / 1.000 / 0.000 / 0.000.
- Covered-case precision and recall Wilson 95%: `[0.700855, 1.0]`.
- Standalone abstain-aware hard contradiction recall: 9/12 = 0.750,
  Wilson 95% `[0.467695, 0.911058]`.
- Baseline-preserving fallback precision/recall/FPR/FNR:
  1.000 / 1.000 / 0.000 / 0.000.
- Hard errors allowed: 0/12; the three invalid typed-ledger negatives abstain and
  retain their baseline rejection.
- Repair fact preservation: 3/3 repair-fact-change cases rejected.
- Probable false positives reduced offline: 1 (`跌进门内`).
- Cost: 0 fixture transport calls, 0 provider calls, model/judge tokens N/A.
- Decision: `ACCEPT_MEASUREMENT`.
- Rollback: not required.

## Interpretation

Positive class is reject. The 25-case signal-backed baseline has TP/FP/TN/FN =
12/1/12/0. The typed candidate covers 22 cases with 9/0/13/0; it abstains on three
hard negatives whose declared payload cannot be legally typed. An abstention is not
an acceptance: the comparison path preserves the existing Guard result, producing
12/0/13/0.

The candidate does not use CanonicalFact. It validates trace completeness, typed
pre/end state and required endpoints before consulting structured verifier fields;
the verifier summary reason never overrides typed/prose evidence. This is why the
fully typed “Alice和Bob一起跌进门内” case is accepted offline despite the current
deterministic phrase matcher rejecting it.

## Gate

All sample, coverage and fallback-quality gates pass except independent review:

- decisive cases: 59 / 50;
- signal-backed rejects: 12 / 12;
- signal-backed accepts: 33 / 20;
- typed coverage: 88% / 70%;
- hard-negative categories with at least three cases: 9 / 6;
- independently reviewed decisive cases: 0 / 20.

Therefore the authoritative decision is `BLOCK_BEHAVIOR_CANDIDATE`. Iterations
23–25 are not executed: no production StateGuard behavior, CanonicalFact consumer
or real-provider replay is implemented.

Artifacts:

- `docs/iter/state_guard_typed_candidate/phase9-typed-candidate-v1.json`
- `docs/iter/state_guard_typed_candidate/phase9-typed-candidate-v1.md`
- report SHA-256:
  `1c9ed43b18dc2cadcf1c406bd0e82db8f8464daf3809b6bbb1b77209210992d7`
