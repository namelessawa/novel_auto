# Iteration 21 — blind adjudication export/import

- iteration_id: `20260721-21-blind-adjudication`
- date: `2026-07-21`
- base_git_sha: `c4ea5c0`
- candidate_git_sha: `ebccd3d`

```text
Iteration: 21
Evidence gap:
The 25 new complete Guard cases have fixture labels but no reviewer-blind packet,
no independently frozen review format and no reproducible agreement calculation.

Hypothesis:
A packet built only from pre-state, required end states, prose, declared typed
ledger, location context and knowledge boundaries can support independent review
without leaking production/verifier decisions or fixture membership.

Single primary change:
Add separate export and import tools, a neutral packet, a withheld audit key and a
blank review template.

Behavior changed:
None. No runtime module imports either script.

Expected metric:
All 25 complete cases export with opaque IDs; no decision/label/source leakage;
pairwise raw agreement, Cohen's kappa and taxonomy disagreement are reproducible.

Safety risk:
Source order, case IDs, filenames or nested trace fields could reveal labels;
model/project reviews could be miscounted as independent human ground truth.

Cost:
0 provider calls; 0 model tokens; no reviewer or judge call.

Validation:
Recursive forbidden-field checks, hidden fixture-ID checks, packet/key hash binding,
known-vector kappa test and two provisional-review import test.

Rollback condition:
Any label leakage, hash mismatch, incomplete case export, or non-human review
unlocking the behavior gate.
```

## Result

- Tests: 7 focused Phase 9 tests passed; final full backend validation is deferred
  to the Phase 9 gate.
- Dataset coverage: 98 planned total, 59 decisive, 39 ambiguous (39.8%).
- Signal-backed accepts/rejects: 33 / 12 after carrying Phase 8 evidence.
- Independent reviews: 0.
- Typed candidate coverage: deferred to Iteration 22.
- Precision/recall/FPR/FNR/abstain: deferred to Iteration 22.
- Hard errors allowed: unchanged at 0/12 hard-negative cases.
- Probable false positives reduced: 0; behavior was not changed.
- Cost: 0 provider calls, model tokens N/A, reviewer tokens N/A.
- Decision: `ACCEPT_INFRASTRUCTURE`.
- Rollback: not required.

## Blindness and provenance

- Packet: `docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json`
- Withheld key: `docs/iter/state_guard_adjudication/phase9-blind-key-v1.json`
- Review template: `docs/iter/state_guard_adjudication/phase9-review-template-v1.json`
- Complete exported cases: 25 / 25.
- Packet SHA-256:
  `fe80127aa1c46313b92e0d47c9e2fa776612df462bd3fbb89e09bdb6eda33ef5`

The reviewer packet contains no fixture IDs, source filenames, expected decisions,
expected error taxonomy, StateGuard final decision, verifier rounds, verifier safe
value, baseline/candidate label or experiment hypothesis. Source-suite order is
removed by content-hash sorting before opaque IDs are assigned.

The audit key is intentionally separate and marked withheld. `human` reviews count
toward the independent-review gate; `independent_model` and `project_agent` reviews
remain provisional. No completed review was fabricated for this iteration, so raw
agreement and Cohen's kappa remain unavailable for the real packet.
