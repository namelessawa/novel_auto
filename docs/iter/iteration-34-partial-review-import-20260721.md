# Iteration 34 — partial review merge and coverage

```text
Iteration: 34
Evidence gap:
The Phase 10 importer requires one file to contain every case, making partial human
work or sharded model results unusable.

Hypothesis:
Hash-bound non-overlapping parts can merge safely when reviewer identity, packet,
type and evidence mode match exactly.

Single primary change:
Add partial review schema, strict merge validation, source/timestamp retention and a
coverage report without weakening the final independent-review Gate.

Provider calls allowed: no
Authorized budget: 0
Expected benefit: valid partial work survives later failure or pause
Safety risk: duplicate/conflicting cases or mixed reviewer identities are combined
Validation: 11+10 case merge, duplicate rejection and metadata mismatch rejection
Rollback condition: duplicate case accepted or provenance lost
```

## Result

- A deterministic test merge of 21 cases reports 21 completed, 4 missing and 21
  decisive; this is a test vector, not an independent review.
- Duplicate case IDs are rejected even when payloads match.
- Reviewer ID/type/evidence/model/provider and packet mismatches are rejected.
- Each part retains its hash, source path and own timestamps.
- Actual human parts imported: 0.
- Decision: `ACCEPT_INFRASTRUCTURE`.
- Rollback: not required.
