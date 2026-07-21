# Iteration 33 — executable human-review packages

```text
Iteration: 33
Evidence gap:
Phase 10 had JSON model templates but no package a human could fill without Python.

Hypothesis:
Two isolated Markdown/CSV/JSON packages can make human review the zero-model-cost
priority while retaining hash-bound case material.

Single primary change:
Add human package export/import with immutable instructions/case hashes, mutable
review templates, strict human metadata and full coverage validation.

Provider calls allowed: no
Authorized budget: 0
Expected benefit: directly distributable human blind review
Safety risk: expected labels or fixture identities leak into package text
Validation: recursive content scan, manifest/file hash checks and filled CSV import
Rollback condition: any label/key leak or acceptance of incomplete invalid rows
```

## Result

- Packages: `phase11-human-a` and `phase11-human-b`.
- Each package: 25 cases and five files (`instructions.md`, `cases.md`, `review.csv`,
  `review.json`, `manifest.json`).
- Human completed/model completed: 0 / 0.
- Leak scan: no expected decision, baseline/candidate decision, verifier flag,
  fixture ID, provider URL, API key or Authorization marker.
- Provider calls / known tokens / uncertain upper bound: 0 / 0 / 0.
- Decision: `ACCEPT_INFRASTRUCTURE`.
- Rollback: not required.
