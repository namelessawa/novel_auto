# Phase 9 status

Updated: 2026-07-21

- Status: `ITERATIONS 18-20 ACCEPTED; ITERATION 21 NEXT`
- Starting HEAD: `a66eb80c7e413439dddf23eea48180059a4cccd4`
- Production behavior changes accepted: none
- Real LLM calls: 0
- Current gate: blind independent adjudication packet
- StateGuard behavior candidate: blocked
- CanonicalFact consumer: blocked and disabled

## Baseline

- Backend: `1294 passed, 1 existing warning` at the Phase 8 final validation.
- Dataset: 73 total, 34 decisive, 39 ambiguous.
- Signal-backed decisive accepts/rejects: 20 / 0.
- Independent human-reviewed cases: 0.
- Typed candidate coverage: 0.

## Trace-loss audit

- Original post-parse Narrator draft is not explicitly identified in the Guard
  trace.
- `before`/`after` store normalized verifier findings, not the complete verifier
  input and raw response.
- `repair_declared` stores only the repair summary; complete repair prose/state is
  lost from the trace.
- Critique rounds omit `text_before` and `text_after` from `to_dict()`.
- CanonicalFact before/after exists in replay rows but is not bound into one
  versioned Guard decision trace with completeness fields.
- Missing payloads have no common schema for denominator filtering.

## Safety

- Iteration 18 is measurement-only.
- No existing Phase 7 trace is relabeled.
- No provider configuration or credential is required.
- No production data, migration, remote push, PR or deploy is authorized.

## Iteration 18 result

- Candidate: `4681754`.
- Decision: `ACCEPT_MEASUREMENT`.
- Added strict `state-guard-trace-v1` with original draft/ledger, complete verifier
  and repair rounds, deterministic checks, Critic provenance, location/knowledge
  context and explicit payload completeness.
- Full-runtime replay binds CanonicalFact before/after after real Orchestrator
  persistence; runtime report schema is now `runtime-replay-v2`.
- Recorded artifact has no missing completeness field; Critic and repair are
  explicitly skipped/not required for this short accepted fixture.
- Tests: 90 focused; full backend `1297 passed, 1 existing warning`.
- Cost: 0 provider calls, 0 model tokens.

## Iteration 19 result

- Candidate: `23a6189`.
- Decision: `ACCEPT_MEASUREMENT`.
- Complete hard-negative suite: 12 expected reject, 12 actual reject, zero hard
  errors allowed.
- Each case traversed full TickRuntime/Orchestrator and StateGuard with 3 verifier
  and 2 full repair rounds; all completeness flags are 12/12.
- Critic executed in one fixture and retained complete input/output.
- Major hard-negative categories each have at least three decisive fixtures.
- Signal-backed decisive accepts/rejects after carrying Phase 8 evidence: 20 / 12.
- Independent reviews: 0; behavior changes remain blocked.
- Tests: 40 focused; full backend `1299 passed, 1 existing warning`.
- Cost: 121 fixture calls, 0 provider calls, model tokens N/A.

## Iteration 20 result

- Candidate: `730b151`.
- Decision: `ACCEPT_MEASUREMENT`.
- Complete expected-accept suite: 13 signal-backed cases, 12 baseline accepts and
  one fully captured deterministic false reject (`跌进门内`).
- Combined planned dataset: 98 total, 59 decisive, 39 ambiguous (39.8%).
- Signal-backed decisive accepts/rejects: 33 / 12.
- Evidence-extraction and reasonable-omission categories each have at least three
  decisive fixtures.
- All completeness flags are 13/13; the false reject includes 3 verifier and 2 full
  repair rounds.
- Independent reviews remain 0; behavior changes remain blocked.
- Tests: 14 focused; full backend `1301 passed, 1 existing warning`.
- Cost: 82 fixture calls, 0 provider calls, model tokens N/A.
