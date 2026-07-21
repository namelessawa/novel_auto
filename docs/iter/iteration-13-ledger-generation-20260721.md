# Iteration 13 — typed ledger generation and raw-audit persistence

- iteration_id: `20260721-13-ledger-generation`
- date: `2026-07-21`
- base_git_sha: `3e77073`
- candidate_git_sha: `078ad1b`

```text
Iteration: 13
Observation:
The typed contract exists but Narrator still requests and persists an arbitrary
continuity_state dictionary. Existing StateGuard and CanonicalFact projection also
expect the legacy field names.

Root cause:
There is no production normalization boundary carrying schema provenance, reference
catalogs and raw audit data, and no conservative compatibility view for existing
readers.

Primary hypothesis:
Narrator can request TypedContinuityState v1, validate it against IDs already in its
scene context, persist both the normalized result and raw audit, and feed a
conservative legacy view to existing StateGuard/projection without changing their
acceptance rules.

Single behavioral change:
Change the Narrator continuity output schema to typed v1 and persist its validation
audit. StateGuard and CanonicalFact continue to receive the compatibility view.

Measurement-only changes:
Record source schema, typed validity, reference issues, authoritative eligibility,
raw payload and prompt-schema marker in NarratorOutput/TickState/replay telemetry.

Expected benefit:
Valid generated ledgers separate location/movement/support and become measurable;
legacy or malformed responses remain readable and auditable instead of crashing or
being silently treated as typed authority.

Safety risk:
The compatibility bridge could accidentally treat in-transit as arrived, project an
unknown field as an objective fact, or make old persisted states unreadable.

Cost estimate:
0 real-model tokens for this iteration; mock and recorded fixtures only.

Validation:
Typed prompt/schema parsing, valid-ID catalogs, raw-audit round trip, legacy fallback,
unknown omission from compatibility projection, full-runtime typed fixture, rejected
projection safety, focused and full backend suites.

Rollback condition:
Any changed StateGuard acceptance for equivalent legacy input, loss of old TickState,
unknown/in-transit data projected as an arrived/objective fact, raw audit loss,
schema prompt growth beyond a bounded structural block, or production test failure.
```

## Result

- Tests:
  - typed/full-runtime focused gate: `60 passed`
  - Narrator/Orchestrator compatibility gate: `93 passed`
  - backend full: `1285 passed, 1 existing warning`
- Recorded replay:
  - artifact: `phase8-runtime-replay-typed-recorded-20260721.json`
  - full-runtime path: accepted, all expectations passed
  - typed ledger valid: `1/1 (100%)`
  - authoritative reference validation: `1/1`
  - raw audit retained: `1/1`
  - provider calls/tokens: `0 / 0`
  - stable evidence SHA-256 (two independent processes):
    `65bc64b8f3c9210a9797373ac0f7ae85459d44e2f7a7d2fa05074b76c79ce2c1`
- Real runtime: no real-model run; recorded responses traversed the real runtime.
- Baseline: legacy output remains readable and receives the same compatibility view.
- Candidate: typed v1 requested by default; typed/raw/audit persisted atomically in
  TickState; old StateGuard/projection consume a conservative legacy view.
- Hard contradictions allowed: 0 in deterministic/recorded counterexamples.
- Probable false positives reduced: not claimed; StateGuard logic is unchanged.
- Typed ledger valid rate: `100%` on the single recorded typed fixture; real-model
  compliance remains unmeasured and is not generalized from this fixture.
- Token delta: 0 measured model tokens. Static system prompt is 2,891 characters,
  +33 (+1.2%) from the Iteration 12 baseline; the dynamic typed ID/schema block is
  419 characters in the minimal fixture.
- Latency delta: not interpreted from local fixture transport.
- Decision: `ACCEPT_BEHAVIOR` for the schema/persistence boundary only.
- Rollback status: not rolled back.

Findings and safety properties:

- The first typed full-runtime attempt found that the old depth-4 compactor changed
  `InjuryState` objects into strings. The cap was moved to depth 6 while retaining
  existing per-container and per-string limits; this regression now has coverage.
- The first independent replay also exposed set-order variation in affected
  characters. Replay scope now sorts that list and restores production behavior
  afterwards; two separate processes produce identical evidence hashes.
- A typed state is authoritative-eligible only when all context ID catalogs are
  present and no reference issue exists. An invalid typed state is hidden from
  legacy StateGuard and CanonicalFact projection rather than guessed.
- `in_transit` is not projected as `arrived`; unknown item condition and ambiguous
  multiple holders are not converted to singular objective fields.
- Guard-safe, unrepaired output retains the typed primary state. A guard-adopted
  repair uses the existing legacy repair schema and is explicitly downgraded to a
  non-authoritative legacy audit instead of being mislabeled typed.
- Old TickState files synthesize a non-authoritative legacy audit on load; no data
  migration is performed.

Acceptance reason:

This is a bounded production schema change with deterministic compatibility and
fail-safe evidence. It does not alter StateGuard acceptance rules or enable a new
fact consumer. The single recorded fixture proves control flow, not real-model
schema adherence or prose-quality improvement; those remain gated behind the
calibration work in Iterations 14-15.
