# Iteration 10 — deterministic full-runtime replay

- iteration_id: `20260721-10-runtime-replay`
- date: `2026-07-21`
- base_git_sha: `7f8f7e3141a3ffaf0106d8867a4bc271ef1c8220`
- candidate_git_sha: `df54a4f`

```text
Iteration: 10
Observation:
Existing style validation bypasses the production Tick path. Existing Orchestrator
tests do not emit a reusable replay artifact or reconciliation report.

Root cause:
There is no versioned fixture contract and no isolated TickRuntime entry point for a
fixed event/response sequence.

Primary hypothesis:
A fixture-driven, agent-id-routed mock can exercise the real TickRuntime and
Orchestrator deterministically without changing production Tick behavior.

Single behavioral change:
None. Add an isolated replay-only TickRuntime constructor and an offline harness.

Measurement-only changes:
Record execution coverage, guard decisions, persistence, CanonicalFact diff,
reconciliation, token/call count and latency.

Expected benefit:
CI can prove accepted StatePatch, NarrativeStateGuard, narrative persistence and
CanonicalFact projection/reconciliation in one reproducible command.

Safety risk:
The harness could accidentally use production data, silently bypass a component, or
label a partial path as full runtime.

Cost estimate:
0 real-model tokens; deterministic local execution only.

Validation:
New fixture/schema tests, accepted and rejected Tick tests, byte-stable report test,
focused replay/Orchestrator tests, then the full backend suite.

Rollback condition:
Any production caller changes behavior; replay can address non-isolated data; a
rejected Tick projects guarded narrative facts; required execution flags are false;
or existing tests regress.
```

## Result

```text
Tests:
4 new replay tests; 34 focused tests passed; full backend 1258 passed with the one
existing Starlette/httpx warning.

Recorded replay:
Not started in Iteration 10.

Real runtime:
The actual TickRuntime/Orchestrator component graph was executed with deterministic
fixture transport. No provider call was made.

Baseline:
No standalone full-runtime replay artifact, no fixture schema, no reconciliation
output, and style validation bypassed the runtime.

Candidate:
1 accepted Tick; 6 fixture calls; 0 tokens; 13 CanonicalFact additions; 15
reconciliation checks; 0 hard conflicts and 0 coverage gaps. All responses consumed.

Hard contradictions allowed:
0 in the accepted fixture. A separate rejection test proves rejected prose does not
project guarded_narrative facts.

Probable false positives reduced:
Not a behavior iteration; not measured.

Typed ledger valid rate:
Not applicable; Iteration 12 prerequisite not started.

Token delta:
0 real-model tokens and no production Tick call added.

Latency delta:
Mock artifact total 0.113 seconds; not a production performance comparison.

Decision:
ACCEPT_INFRASTRUCTURE

Rollback status:
Not required. Replay directory override is private, restricted to user_id
`__replay__`, and covered by a fail-closed test.
```

## Demonstrated execution coverage

| Component | Evidence |
| --- | --- |
| TickRuntime | real component assembly used |
| Orchestrator | `run_tick()` completed |
| WorldSimulator | fixture response consumed |
| EventInjector | fixture response and StatePatch consumed |
| CharacterAgent | two production agents executed |
| ActionResolver | production resolver invoked once |
| StatePatch | one accepted patch applied and projected |
| Narrator | fixture response consumed |
| Critic | not configured for the short deterministic fixture; explicitly false |
| StateGuard | production guard verified and accepted |
| Persistence | TickState, narrative, TickDB and sidecar exist |
| CanonicalFact | 13 deterministic additions |
| Reconciliation | 15 checks, zero findings |

The harness also runs a rejected fixture in tests: it performs two bounded repairs,
rejects after independent verification, persists authoritative Event/Action/Patch
facts, writes no narrative, and writes no `guarded_narrative` fact.
