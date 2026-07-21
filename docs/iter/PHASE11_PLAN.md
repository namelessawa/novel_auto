# Phase 11 plan — sharded review, human gold and recoverable replay Gate

Date: 2026-07-21

Branch: `codex/longtext-style-iteration-20260721`

Starting HEAD: `0399476b936c446317371dfddb8574aef07daea8`

Phase 10 verdict: `INCONCLUSIVE`

## Authorized scope

- New reviewer-model budget: 0 tokens.
- Provider calls allowed: no.
- Complete Iterations 31–35 only where no model call or fabricated human answer is
  required.
- Produce sharded task/checkpoint infrastructure, recorded/mock verification,
  human-review packages, partial merge and Gold Gate tooling.
- Stop before real replay, typed production behavior and CanonicalFact consumption
  unless two independent reviews later pass the Gate.

## Ordered hypotheses

1. A deterministic 1–3-case task definition can make one bad response local rather
   than invalidating all 25 cases.
2. Atomic per-case checkpoints plus one local format retry can make resume safe and
   budget-accountable.
3. Markdown/CSV/JSON packages can obtain human labels without Python or model cost
   while preserving the blind boundary.
4. Non-overlapping partial files can be merged without losing provenance or
   accepting duplicate/conflicting cases.
5. Gold labels can be hash-stable and immutable, while the current zero-review
   state continues to return `BLOCK_REAL_REPLAY`.

## Stop boundary

The Phase 10 conservative historical upper bound (62,140 tokens) is retained
separately. It is not reclassified as Phase 11 budget. With no new authorization,
the capability probe and all provider/model calls remain disabled. Human packages
are deliverables, not completed reviews.

No StateGuard threshold/regex, Narrator, SummaryTree, StylePreset, typed production
path, CanonicalFact consumer, `old/`, production data or remote repository operation
is in scope.
