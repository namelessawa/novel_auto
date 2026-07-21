# Iteration 15 — failure taxonomy and calibration metrics

- iteration_id: `20260721-15-failure-taxonomy`
- date: `2026-07-21`
- base_git_sha: `2d78153`
- candidate_git_sha: `6882f8c`

```text
Iteration: 15
Observation:
The calibration set has 73 provisional labels, but 39 are ambiguous. Among the 34
decisive labels, only 20 have recorded Phase 7 verifier/deterministic/combined
signals, and all 20 are expected accepts.

Root cause:
Missing rejected drafts prevent adjudicating the 36 Phase 7 rejects, while the 17
minimal counterexamples do not contain recorded verifier calls. Confusion metrics
can therefore measure false rejects on known accepts but cannot measure hard-error
recall.

Primary hypothesis:
A coverage-aware calibration report that returns null for unsupported metrics and
separates provisional-label quality metrics from recorded-outcome reproduction can
prevent an unjustified StateGuard behavior change.

Single behavioral change:
None. Add deterministic metric/taxonomy tooling and reports only.

Measurement-only changes:
Confusion matrices for verifier, deterministic gate and combined decision; explicit
coverage/undefined reasons; ambiguous rate; repair success/fact preservation;
operational reproduction (not ground truth); behavior-gate verdict.

Expected benefit:
The report identifies whether Iteration 16 has enough hard-negative evidence and
which Phase 7 failure classes need complete prose or human adjudication.

Safety risk:
Undefined precision/recall could be silently coerced to zero/one, ambiguous cases
could be counted as negatives, or combined-decision reproduction could be presented
as quality accuracy.

Cost estimate:
0 real-model tokens.

Validation:
Hand-checked confusion counts; ambiguous exclusion; null metric reasons; repair
statistics; deterministic JSON/Markdown; full backend suite.

Rollback condition:
Any ambiguous case included in quality confusion, tautological reproduction labeled
ground truth, unsupported metric emitted as numeric, nondeterministic report, or
production behavior change.
```

## Result

- Tests:
  - calibration dataset + metrics: `9 passed`
  - backend full: `1294 passed, 1 existing warning`
- Recorded replay: all 56 Phase 7 signal rows analyzed without a new model call.
- Real runtime: not run because the behavior gate failed before Gate B2.
- Baseline: recorded outcomes could be compared but unsupported denominators and
  ambiguous labels were not separated into a formal report.
- Candidate: coverage-aware JSON/Markdown calibration report with explicit nulls and
  a blocking behavior gate.
- Hard contradictions allowed: cannot be measured; no decisive reject has recorded
  verifier/deterministic/combined signals.
- Probable false positives reduced: not changed. The report identifies 31
  verifier-safe/deterministic-reject cases as probable evidence failures, but they
  remain unconfirmed because rejected drafts are absent.
- Typed ledger valid rate: typed decision candidate coverage is 0 in the calibration
  set; no metric is fabricated.
- Token delta: 0.
- Latency delta: 0 in production.
- Decision: `ACCEPT_MEASUREMENT`; Iteration 16 behavior candidate blocked.
- Rollback status: no behavior experiment was started.

Quality confusion (positive class = reject; ambiguous excluded):

- Signal coverage: 20/34 decisive cases (58.8%); all 20 are expected accepts.
- Verifier: TP 0, FP 1, TN 19, FN 0; precision 0.0, recall unavailable,
  FPR 5%, FNR unavailable.
- Deterministic evidence gate: TP 0, FP 4, TN 16, FN 0; precision 0.0,
  recall unavailable, FPR 20%, FNR unavailable.
- Combined final decision: TP 0, FP 0, TN 20, FN 0; precision and recall
  unavailable, FPR 0%.
- Typed-ledger candidate: unavailable, 0 evaluated cases.
- Ambiguous: 39/73 (53.4%).

Operational reproduction (not ground truth):

- Verifier vs recorded outcome: precision 83.3%, recall 13.9%, FPR 5%.
- Deterministic gate vs recorded outcome: precision 90%, recall 100%, FPR 20%.
- Combined decision exactly reproduces its own recorded outcome target. This is
  tautological operational evidence and is explicitly not quality accuracy.

Repair:

- Attempts: 40.
- Adopted/successful: 4 (10%).
- Recorded fact preservation: 32/40 (80%).
- Fact change or unknown preservation: 8/40.

Behavior gate: `BLOCK_BEHAVIOR_CANDIDATE`

- Only 34 decisive labels; the behavior gate requires 40.
- No labeled reject has recorded verifier/deterministic/combined signals.
- No label has independent human review.
- Typed-ledger candidate decision coverage is zero.

Report SHA-256:
`b4d6f86a0c1b9c12c14ab5d82903317b4763185afd7fde549606c5c0c636dddc`.

Acceptance reason:

The metric layer is reproducible and refuses to overstate evidence. Because hard
contradiction recall is unmeasurable, Phase 8 must stop before changing StateGuard or
enabling CanonicalFact read-only consumption. This also completes six effective
iterations (10-15), satisfying the earlier stop condition.
