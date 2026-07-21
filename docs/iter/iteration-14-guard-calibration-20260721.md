# Iteration 14 — StateGuard calibration dataset

- iteration_id: `20260721-14-guard-calibration`
- date: `2026-07-21`
- base_git_sha: `e04acd9`
- candidate_git_sha: `7b21385`

```text
Iteration: 14
Observation:
Phase 7 supplies 56 guard outcomes, but recorded production decisions are not ground
truth and all 36 rejected cases lack the complete rejected Narrator draft. Known
counterexamples are distributed across tests rather than one reviewable dataset.

Root cause:
There is no versioned calibration schema separating source completeness, recorded
signals, reviewer labels, adjudication status and error taxonomy.

Primary hypothesis:
A loss-aware dataset combining all 56 Phase 7 traces with minimal synthetic
counterexamples can cover the required taxonomy and support reproducible calibration
without converting missing prose into confident accept/reject labels.

Single behavioral change:
None. Add dataset builder, curated minimal cases, generated artifact and validation
tests only.

Measurement-only changes:
Add two explicit Codex-assisted rubric passes, agreement/adjudication fields,
human_reviewed=false, decoded review views for known mojibake, source hashes,
completeness and label distributions.

Expected benefit:
Iteration 15 can calculate signal metrics on decisive labels, report ambiguous and
coverage rates separately, and identify which Phase 7 failures cannot be resolved
without missing prose or human review.

Safety risk:
Recorded rejects could be mislabeled true positives, generated labels could be
misrepresented as independent human review, or mojibake repair could overwrite raw
evidence.

Cost estimate:
0 real-model tokens.

Validation:
At least 40 unique labeled cases; exact source hashes; two review records per case;
all required error types; deterministic bytes/hash; raw evidence retained by source
reference; missing rejected drafts remain ambiguous; full backend suite.

Rollback condition:
Any fabricated missing prose, human-review claim, lost source hash, fewer than 40
labels, missing taxonomy category, nondeterministic artifact or production change.
```

## Result

- Tests:
  - calibration dataset: `5 passed`
  - backend full: `1290 passed, 1 existing warning`
- Recorded replay: no replay decision changed; all 56 Phase 7 cases imported by
  source hash.
- Real runtime: not run; no generation or judge calls are required for curation.
- Baseline: 56 recorded production outcomes with no ground-truth label boundary and
  36 missing rejected drafts.
- Candidate: 73-case versioned calibration dataset with dual provisional reviews,
  completeness, recorded signals, error taxonomy and decoded review views.
- Hard contradictions allowed: not evaluated in this measurement-only iteration.
- Probable false positives reduced: not claimed.
- Typed ledger valid rate: not applicable.
- Token delta: 0.
- Latency delta: 0 in production.
- Decision: `ACCEPT_MEASUREMENT`.
- Rollback status: not rolled back.

Dataset summary:

- Total: 73; Phase 7 recorded: 56; minimal synthetic: 17.
- Provisional labels: 27 accept, 7 reject, 39 ambiguous; decisive cases: 34.
- Dual Codex-assisted rubric passes: 73/73; agreement: 73/73.
- Human-reviewed labels: 0. The artifact explicitly marks
  `human_reviewed=false`; the dual passes are reproducible review aids, not
  independent human ground truth.
- Phase 7 recorded accepts: 20 provisional accepts because full accepted text is
  available in the pinned source and no recorded contradiction survived.
- Phase 7 recorded rejects: all 36 remain ambiguous because complete rejected
  drafts and repair bodies were not retained. No absent prose was synthesized.
- All required error categories have at least one case.
- Dataset SHA-256:
  `573b2d822b8ecc3d4caf2609781d1fa2c26cd3ced46e8b25eba4f8dcc5b43441`.
- Source hashes:
  - Phase 7 conversion:
    `c495d3c8a791d6ac698594c4e9b97ff8bff5e6c86059d66bea856be7b5d07be2`
  - Minimal curated cases:
    `bc94e2cb9269ae58df1b654075f92867543a7a37e8bea2752ea65518307839e9`

Reviewability:

- Known CP1252/Latin-1→GBK mojibake is decoded only into a derived review view when
  the CJK score improves. The source reference, raw artifact and hash remain
  unchanged.
- Every case separates recorded signals from expected labels and includes source
  completeness. Metrics can therefore exclude ambiguous cases without silently
  counting them as negatives.

Acceptance reason:

The dataset exceeds the 40-case requirement, covers the requested taxonomy and is
deterministic and loss-aware. It is accepted as measurement infrastructure only.
The absence of human review and the 39 ambiguous labels are mandatory limitations
for Iteration 15 metrics and prevent a production threshold claim.
