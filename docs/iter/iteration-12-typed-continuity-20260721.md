# Iteration 12 — typed continuity contract and legacy fallback

- iteration_id: `20260721-12-typed-continuity`
- date: `2026-07-21`
- base_git_sha: `54ffedb`
- candidate_git_sha: `3aeafb5`

```text
Iteration: 12
Observation:
continuity_state is an arbitrary dictionary. Character location may contain an
action/support phrase, item holder may be a pronoun, injuries change shape across
Ticks, and knowledge entries have no stable fact reference.

Root cause:
The current contract compacts JSON size but does not validate field meaning, entity
IDs, schema version or cross-field shape. Legacy state and validated state are also
indistinguishable to consumers.

Primary hypothesis:
A strict Pydantic typed contract plus a deliberately non-authoritative legacy
normalization result can separate location, movement, support, injury, item and
knowledge identity without breaking old novels or inventing facts.

Single behavioral change:
None in the production Tick path. Add the typed contract, reference validation and
legacy fallback library only; Narrator/TickState integration is reserved for
Iteration 13.

Measurement-only changes:
Expose validation issues, provenance, authoritative eligibility, unmapped legacy
paths and retained raw JSON-safe audit payload.

Expected benefit:
Iteration 13 can adopt a well-tested schema, while unknown or ambiguous legacy
values remain observable and cannot silently become authoritative facts.

Safety risk:
An over-eager legacy parser could convert natural-language motion or support into a
location ID, or mark inferred values authoritative.

Cost estimate:
0 real-model tokens.

Validation:
Strict typed round-trip; action phrase rejected as location ID; support separated;
legacy raw retained; unknown references and malformed typed input fail safe; full
backend suite.

Rollback condition:
Any legacy read failure, guessed ID, loss of raw audit payload, ambiguous normalized
value marked authoritative, production consumer activation, or CanonicalFact
projection from unknown data.
```

## Result

- Tests:
  - typed continuity: `12 passed`
  - focused continuity/projection/reconciliation: `33 passed`
  - backend full: `1275 passed, 1 existing warning`
- Recorded replay: not rerun; no replay behavior changed.
- Real runtime: not run; this iteration has no production consumer.
- Baseline: arbitrary compacted dictionary, no schema provenance or reference
  eligibility signal.
- Candidate: strict `TypedContinuityState` v1 plus loss-aware normalization result.
- Hard contradictions allowed: not measured; StateGuard unchanged.
- Probable false positives reduced: not claimed; StateGuard unchanged.
- Typed ledger valid rate: not measured until Narrator generation in Iteration 13.
- Token delta: 0.
- Latency delta: 0 in production; no consumer activated.
- Decision: `ACCEPT_INFRASTRUCTURE`.
- Rollback status: not rolled back.

Accepted contract:

- Stable IDs are syntax-validated and separately checked against supplied character,
  location, item, fact, open-loop and source-event catalogs.
- Location uses `location_id`, `movement_status` and
  `destination_location_id`; support/carriage use distinct fields.
- Injuries have stable ID, body part, severity, lifecycle status and source event.
- Items have explicit holders, location, non-negative numeric quantity, condition
  enum and optional container.
- Knowledge references stable fact IDs rather than free prose.
- Typed input is authoritative-eligible only after all reference catalogs are
  supplied and no reference issue remains.
- Legacy input is always non-authoritative. Stable IDs may be copied into a typed
  view, while natural-language locations, injuries, holders, conditions and
  unattributed knowledge remain unmapped diagnostics.
- The full original payload is retained as JSON-safe audit data. Malformed input,
  non-JSON objects and non-finite numbers fail safe without raising through the
  normalizer.

Acceptance reason:

The contract makes ambiguity measurable without activating a consumer or changing
facts. It passes backward-compatible fallback cases and keeps unknown data from
becoming authoritative. Narrator/TickState generation and raw-audit persistence are
explicitly deferred to Iteration 13.
