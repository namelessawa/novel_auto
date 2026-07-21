# Iteration 20 — complete probable-false-positive replay

- iteration_id: `20260721-20-probable-fp-replay`
- date: `2026-07-21`
- base_git_sha: `bfc103f`
- candidate_git_sha: `730b151`

```text
Iteration: 20
Evidence gap:
The hard-negative suite supplies recall denominators but no complete expected-accept
cases for measuring false rejection, omission, group movement, lies or rumors.

Hypothesis:
At least eight complete expected-accept fixtures can measure baseline false rejects;
thirteen fixtures also bring the combined ambiguous rate below 40% without relabeling
missing Phase 7 drafts.

Single primary change:
Add 13 complete expected-accept full-runtime fixtures and preserve fallback verifier
and repair payloads when the deterministic layer overrides reported_safe.

Behavior changed:
None. The existing deterministic Guard is allowed to reject a provisional expected
accept so the false-positive baseline remains visible.

Expected metric:
13 signal-backed expected accepts, zero payload loss, evidence-extraction and
reasonable-omission categories each covered at least three times.

Safety risk:
Fixture geography could conflict with production preflight, an expected accept could
be forced through by changing Guard logic, or unused fallback responses could be
misreported as provider calls.

Cost:
0 provider calls; fixture tokens N/A.

Validation:
Reproducible builder, actual full runtime, explicit baseline decision changes,
complete repair path for false rejects, category/combined-rate tests and full suite.

Rollback condition:
Payload loss, hidden hard error, production behavior change, combined ambiguous rate
above 40%, provider call or backend regression.
```

## Result

- Tests: 14 focused passed; full backend `1301 passed, 1 existing warning`.
- Dataset coverage after planned merge: 98 total = 73 Phase 8 + 12 hard negatives
  + 13 expected accepts; 59 decisive, 39 ambiguous (39.8%).
- Signal-backed decisive accepts/rejects: 33 / 12 after carrying Phase 8 accepts.
- Independent reviews: 0.
- Typed candidate coverage: deferred to Iteration 22.
- Precision/recall/FPR/FNR/abstain: baseline aggregation deferred to Iteration 22.
- Hard errors allowed: 0/12 hard negatives from Iteration 19; unchanged.
- Probable false positives reduced: 0; one baseline false reject is now fully
  captured, not behaviorally fixed.
- Cost: 82 fixture transport calls, 0 provider calls, model tokens N/A.
- Decision: `ACCEPT_MEASUREMENT`.
- Rollback: not required.

Final suite evidence:

- fixture: `backend/tests/fixtures/runtime_replay/phase9_probable_fp_suite_v1.json`
- report: `docs/iter/phase9-probable-fp-replay-20260721.json`
- expected accepts: 13
- actual accepts/rejects: 12 / 1
- signal-backed expected accepts: 13
- complete traces: 13 / 13
- all eight completeness flags: 13 / 13
- evidence-extraction/reasonable-omission fixtures: 6 / 7
- stable suite evidence SHA-256:
  `6aef1bf2d5fb50d14b81d630913a1d2ff7446a8cb9116651599f8bfec14ce191`

The retained baseline false reject is `phase9-fp-synonym-fall-inside`: prose says
“Alice和Bob一起跌进门内”, both typed locations are `city_gate_inner`, and the
recorded verifier reports safe with exact prose/ledger evidence. The deterministic
semantic check does not recognize “跌进” as completing both participants, so it
rejects after two complete no-fact-change repairs. No threshold or regular expression
was changed.

The first fixture pass produced 9/13 accepts and three missing repair payloads. It
revealed fixture evidence phrases that did not satisfy the existing participant
extractor and one preflight mismatch. The final fixture set supplies complete fallback
rounds, uses production-consistent location names and retains only the intentional
“跌进” false-reject candidate. Failed intermediate artifacts were overwritten, not
presented as final evidence.

