# Phase 8 plan — full runtime, typed continuity and guard calibration

Date: 2026-07-21  
Branch: `codex/longtext-style-iteration-20260721`  
Starting HEAD: `7f8f7e3141a3ffaf0106d8867a4bc271ef1c8220`  
Behavioral baseline: `6477f61b3ade9f3e984f66f457521976106edac9`  
Phase 7 measured candidate: `040ad05`  
Phase 7 verdict: `INCONCLUSIVE`

## Evidence carried forward

- CanonicalFact storage/projection/reconciliation exists and is not a quality claim.
- Phase 7 style validation called `NarratorAgent` directly; it did not execute
  Orchestrator or write `canonical_facts.json`.
- Across 56 Phase 7 pressure ticks: 20 final accepts, 36 rejects, 40 repair
  attempts, 4 adopted repairs. Verifier reported safe on 50/56 initial checks while
  the deterministic gate passed 16/56 initial checks.
- Phase 7 artifacts retain required events, event checks and evidence excerpts for
  all ticks, but rejected Narrator/repair full prose was not persisted. They can
  support decision/evidence replay, not a falsely claimed full-response replay.
- Unrelated untracked `scripts/openai_compatible_chat.py` remains out of scope.

## Production Tick execution path

```text
TickRuntime
  -> Orchestrator.run_tick
  -> WorldSimulator
  -> EventInjector + external fixed Event
  -> CharacterAgent.batch_decide
  -> ActionResolver.resolve
  -> accepted CharacterAction state transitions
  -> EventInjector StatePatch application
  -> NarratorAgent
       -> style gate / Critic when configured
       -> NarrativeStateGuard verify/repair/reverify
  -> safety/preflight
  -> narrative + continuity persistence
  -> CanonicalFact projection append/save
  -> KnowledgeGraph/TickState/TickDB persistence
  -> read-only reconciliation (Phase 8 harness)
```

`validate_styles.py` bypasses TickRuntime, WorldSimulator, EventInjector,
CharacterAgent, ActionResolver, StatePatch application, Orchestrator persistence,
CanonicalFact projection, TickDB and reconciliation.

## Replay fixture schema v1

Required fields:

```json
{
  "fixture_version": "1",
  "fixture_id": "map_gate_full_runtime_tick_1",
  "initial_state": {
    "world_state": {},
    "character_profiles": [],
    "character_states": [],
    "continuity_state": {}
  },
  "canonical_facts_before": [],
  "events": [],
  "responses_by_agent": {},
  "expected_required_end_states": [],
  "expected_fact_transitions": [],
  "expected_acceptance": "accept",
  "labels": []
}
```

Responses are routed by production `agent_id`, not one concurrency-sensitive global
queue. Fixtures contain only synthetic/minimal prose and no credentials or private
novels.

## Gates and budgets

1. Iteration 10: deterministic mock through actual TickRuntime and Orchestrator.
2. Iteration 11: recorded responses and Phase 7 decision/evidence conversion.
3. Iteration 12: versioned TypedContinuityState plus fail-safe legacy normalization.
4. Iteration 13: Narrator output normalization/raw audit; no literary Prompt growth.
5. Iterations 14–15: at least 40 reviewed calibration cases and separate metrics.
6. Iteration 16 behavior candidate only if hard-error recall does not fall.
7. Iteration 17 CanonicalFact read-only StateGuard context only if all prerequisites
   pass; default off. Never inject it into Narrator in Phase 8.

Real generation budget is 200,000 tokens, judge budget 30,000, and any single real
experiment is capped at 40 calls. Mock/recorded work runs first and costs zero model
tokens.
