# Phase 9 plan — Guard ground truth, complete traces and read-only consumers

Date: 2026-07-21

Branch: `codex/longtext-style-iteration-20260721`

Starting HEAD: `a66eb80c7e413439dddf23eea48180059a4cccd4`

Phase 8 evidence HEAD before final verdict: `be7ef77b167e148a48df93bbb43b941537bcf0fd`

Behavioral baseline: `6477f61b3ade9f3e984f66f457521976106edac9`

Phase 8 verdict: `CONDITIONAL PASS`

## Evidence carried forward

- The full-runtime mock/recorded harness, typed continuity v1, legacy fail-safe,
  CanonicalFact projection/reconciliation and the Phase 8 calibration tooling are
  prerequisites, not quality claims.
- Phase 8 has 73 cases, 34 decisive labels, 39 ambiguous labels, 20 signal-backed
  decisive accepts, zero signal-backed decisive rejects and zero independent human
  reviews.
- Existing Phase 7 traces cannot be upgraded into complete negatives because the
  rejected drafts and full repair prose were never retained.
- Real provider replay, Critic replay coverage, typed-candidate decisions and a
  CanonicalFact consumer remain unimplemented or disabled.
- Unrelated untracked `scripts/openai_compatible_chat.py` remains out of scope.

## Ordered iterations

1. Iteration 18: versioned, loss-aware full Guard trace capture. No decision change.
2. Iteration 19: at least 12 complete signal-backed hard-negative recorded fixtures
   through the actual StateGuard control flow.
3. Iteration 20: at least 8 complete probable-false-positive fixtures through the
   same control flow.
4. Iteration 21: blind adjudication export/import and agreement metrics.
5. Iteration 22: offline typed candidate with abstention and coverage-aware metrics;
   never called by the production Guard.
6. Gate review. If independent review or another mandatory denominator is missing,
   stop before Iterations 23–25.

## Non-goals and safety boundary

- Do not change StateGuard thresholds, fail-closed rules, regular expressions,
  StylePreset, SummaryTree or Narrator CanonicalFact context.
- Any future behavior candidate and CanonicalFact consumer must be feature-flagged,
  default off and blocked unless every Phase 9 behavior-gate prerequisite passes.
- Do not synthesize missing Phase 7 prose or call a fixture a real-model result.
- Do not read credentials, `coding.txt` or `.env`; do not push, open a PR, deploy or
  migrate production data.

## Budgets

- Mock/recorded provider calls: 0; fixture tokens remain N/A.
- Real generation budget: 150,000 tokens, judge budget: 20,000 tokens, calls: 40.
- Real mode is not implemented unless the offline and independent-review gates pass.
