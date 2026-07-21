# Iteration 18 — complete StateGuard trace capture

- iteration_id: `20260721-18-full-guard-trace`
- date: `2026-07-21`
- base_git_sha: `a66eb80`
- candidate_git_sha: `4681754`

```text
Iteration: 18
Evidence gap:
Existing traces retain normalized before/after findings and repair summaries, but
not complete verifier inputs/raw outputs, repair prose, pre-Critic Narrator draft,
Critic round prose or one bound CanonicalFact before/after record.

Hypothesis:
A strict, versioned, current-Tick-only trace with explicit completeness flags can
make future negative denominators auditable without changing StateGuard decisions.

Single primary change:
Capture and validate complete Guard payloads; enrich full-runtime replay with the
CanonicalFact snapshots produced after Orchestrator persistence.

Behavior changed:
No acceptance, repair, threshold, regular-expression or production-consumer change.

Expected metric:
Every newly complete replay exposes original draft/ledger, verifier rounds,
deterministic checks, applicable repair/Critic payloads and location context.

Safety risk:
The trace could silently truncate prose, retain whole-novel context, leak provider
secrets, or mark an unattempted repair/Critic as a missing payload.

Cost:
0 provider calls and 0 model tokens; local fixture transport only.

Validation:
Strict Pydantic validation, full repair round trip, payload-loss fixture, real
TickRuntime recorded replay, focused tests and full backend suite.

Rollback condition:
Any changed final decision, incomplete attempted repair, secret marker, unbounded
history capture, invalid old trace reader or backend regression.
```

## Result

- Tests: 90 focused passed; full backend `1297 passed, 1 existing warning`.
- Dataset coverage: unchanged at 73 Phase 8 cases; Iteration 18 adds one trace
  artifact but does not relabel or merge it into calibration.
- Signal-backed accepts/rejects: unchanged 20 / 0.
- Independent reviews: 0.
- Typed candidate coverage: 0.
- Precision/recall/FPR/FNR/abstain: not recalculated; no decision candidate exists.
- Hard errors allowed: 0 in the deterministic accepted fixture and its existing
  rejection regression.
- Probable false positives reduced: 0; behavior unchanged.
- Cost: 6 fixture transport calls, 0 provider calls, 0 model tokens.
- Decision: `ACCEPT_MEASUREMENT`.
- Rollback: not required.

Recorded artifact:

- `docs/iter/phase9-guard-trace-recorded-20260721.json`
- runtime schema: `runtime-replay-v2`
- Guard schema: `state-guard-trace-v1`
- artifact size: 58,110 UTF-8 bytes
- original draft: 74 characters, complete
- verifier rounds: 1 complete input/raw output/normalized output
- repair rounds: 0; repair was not required, not mislabeled as payload loss
- Critic: skipped by length gate; input and skip reason retained
- deterministic checks: complete
- CanonicalFact before/after: 0 / 13
- completeness missing fields: none
- stable evidence SHA-256:
  `df2eff9b179a49beac285e0f5735c9cc2cd33203d81c2b7b39f933e579df5646`

The trace includes only current-Tick draft/state/event/location/knowledge material.
It stores no provider headers or credentials. Full Critic and attempted-repair
coverage remain requirements for Iterations 19–20.
