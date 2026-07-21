# Iteration 23 — independent review freeze attempt

- iteration_id: `20260721-23-independent-review`
- date: `2026-07-21`
- base_git_sha: `8b6b0eb`
- infrastructure_git_sha: `6170106`

```text
Iteration: 23
Evidence:
Phase 9 has 25 complete blind cases but zero independent reviewer submissions.

Hypothesis:
Two isolated external model families can review the hash-bound packet at temperature
0 within the 60,000 reviewer-token budget, without receiving the blind key.

Single primary change:
Strengthen packet questions/repair evidence and review metadata; add secret-safe,
budgeted external review execution plus loss-aware failure checkpoints.

Behavior changed:
None. StateGuard, Narrator, typed candidate and CanonicalFact paths are untouched.

Review requirement:
Two complete human/independent-model submissions over all 25 cases, followed by
agreement/kappa and third-party adjudication when required.

Real-model cost estimate:
Initial packet estimate 19,178 input tokens; content-catalog estimate 7,069; final
lossless table estimate 4,477. Hard total budget remains 60,000.

Safety risk:
Malformed JSON, reasoning tokens consuming the output budget, invalid provider
credentials, correlated reviewer families, label leakage, or unknown failed-call
usage could invalidate both the review and cost denominator.

Validation:
Recursive leak tests, six-question/repair checks, packet/key hash binding, isolated
copy contents, metadata/timestamp validation, reviewer identity checks, coverage and
duplicate rejection, kappa, blind disagreement packet, third-review merge and Gate.

Rollback condition:
Any label/key leakage, fabricated reviewer, budget overrun, missing rationale/case,
or production behavior change.
```

## Result

- Tests: 13 focused tests passed before final suite.
- Independent reviewers: 0 valid; six provider requests produced five model
  responses and no importable full review.
- Agreement: unavailable.
- Kappa: unavailable.
- Gold decisive accepts/rejects: 0 / 0.
- Real reviewed cases: 0.
- Typed coverage/precision/recall/FPR/FNR/abstain: not recalibrated; Phase 9
  synthetic-only values are not promoted.
- Hard errors allowed: not evaluated against independent gold.
- Correct false rejects reduced: 0 production changes.
- Provider requests: 6; model responses: 5.
- Tokens: exact known 26,147; known lower bound excluding the first unknown call
  exceeds 31,547; conservative total upper bound 62,140 against a 60,000 budget.
- Decision: `INCONCLUSIVE`.
- Rollback: no behavior rollback needed; infrastructure and failure evidence kept.

## Failure evidence

1. Coding-compatible `glm-5.2`, expanded packet: malformed JSON. This occurred
   before failure checkpoints; actual usage/raw output are unavailable, bounded by
   24,178 tokens.
2. Coding-compatible `glm-5.2`, catalog packet: 9,392 tokens; all completion budget
   was consumed without final JSON content.
3. `mimo-v2.5-pro`: configured credential rejected before model generation; zero
   model tokens and no key value printed.
4. Ark `glm-5.2`, catalog packet: 8,392 tokens; empty final content.
5. `deepseek-v4-pro`, catalog packet: 8,363 tokens; 1,801 completion tokens but
   empty final content, consistent with reasoning exhausting the output budget.
6. Ark `glm-5.2`, final compact packet with thinking disabled: provider-reported
   usage exceeded the 5,400 per-reviewer limit. Exact usage was lost immediately
   before budget-failure checkpoint capture; conservative upper bound is 11,815.

Every retained failure artifact contains only packet/model/usage metadata and model
output when available. Provider URL, API key and Authorization data are absent. The
blind key was never an API input.

## Gate

Iteration 23 fails the first mandatory threshold: independently reviewed decisive
cases are 0/20, accepts 0/8 and rejects 0/8. The reviewer-token upper bound reaches
or exceeds the 60,000 limit. Therefore:

- Iteration 24 cannot freeze gold labels;
- Iterations 25–30 are blocked;
- no real replay mode is implemented;
- no StateGuard behavior or CanonicalFact consumer is implemented;
- no further provider call is authorized in this phase.
