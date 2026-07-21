# Phase 11 verdict — sharded review and real replay Gate

Date: 2026-07-21

```text
branch: codex/longtext-style-iteration-20260721
phase11_start: 0399476b936c446317371dfddb8574aef07daea8
infrastructure_commit: 278cdae
packet_sha256: 2b28c5c9a11dc04e6971268054bc7296c88a6ff5a1b079105ec7880a09abc4da
new_authorized_model_budget: 0
phase11_provider_calls: 0
production_behavior_changes: 0
```

## 1. Executive summary

### Infrastructure

Phase 11 replaced the all-or-nothing review execution boundary with deterministic
1–3-case tasks, per-case atomic checkpoints, resume, local response validation, one
case-local format retry, a non-blind provider capability probe contract and separate
historical/new budget accounting. It also added two directly fillable human-review
packages, strict CSV/JSON import, partial review merging, coverage reports,
disagreement-only export and immutable Gold Gate tooling.

### Measurement

The checked-in task set contains 25 stable single-case tasks with definition hash
`97fa6e01c2a10636f3a667a0526c1e147f0f06493238cd0010ccc902daafa140`.
Two isolated 25-case human packages were generated. Neither has been filled by an
independent human, so actual completed reviews, overlap, agreement, kappa and gold
labels remain zero/unavailable. Mock/recorded tests are control-flow evidence only
and are explicitly ineligible for the independent Gate.

### Behavior

No StateGuard threshold, regex or decision path changed. No real replay mode, typed
production flag, CanonicalFact consumer, Narrator/SummaryTree input or StylePreset
change was added. The current decision remains `BLOCK_REAL_REPLAY`; Iterations
36–40 were not executed.

### Quality

The review process is now recoverable and human-executable, but no new independently
reviewed fact label or real novel sample exists. This is an infrastructure gain, not
a demonstrated continuity, prose or cross-theme quality improvement.

## 2. Review execution

| Measure | Actual Phase 11 result |
| --- | ---: |
| Tasks | 25 single-case tasks |
| Pending | 25 |
| Completed | 0 |
| Invalid | 0 |
| Provider failed | 0 |
| Budget blocked task executions | 0; provider execution was not started |
| Human packages exported | 2 |
| Human results completed/imported | 0 |
| Model results completed | 0 |
| Format retries | 0 actual; bounded behavior covered by tests |
| Resume count | 0 actual; non-repeat behavior covered by tests |
| Provider capability probes | 0 |

The A/B human packages are separate and shuffled independently. Each contains
`instructions.md`, `cases.md`, `review.csv`, `review.json` and `manifest.json`.
Content scanning found no expected decision, fixture identifier, baseline/candidate
decision, verifier flag, provider URL, API key, Authorization marker or blind-key
file. Human packages are deliverables, not human labels.

Recorded tests demonstrated that a malformed member does not discard a valid
sibling, empty final content is isolated, a format retry contains only the current
case/schema/error type, and completed cases are not called again after resume.
Recorded/mock results cannot enter the independent Gate.

## 3. Cost

| Budget layer | Value |
| --- | ---: |
| Phase 10 historical exact known usage | 26,147 tokens |
| Phase 10 historical conservative upper bound | 62,140 tokens |
| Phase 11 new authorized budget | 0 tokens |
| Phase 11 exact provider usage | 0 tokens |
| Phase 11 unknown usage upper bound | 0 tokens |
| Phase 11 provider calls | 0 |
| Remaining authorized budget | 0 tokens |

Historical usage is retained separately and is not treated as renewed budget. With
new authorization at zero, the runner blocks before provider configuration, secret
loading, client construction or capability probing. Unknown future failures are
defined to consume configured maximum input plus output in the conservative bound;
they can never be charged as zero.

## 4. Gold labels

| Measure | Result |
| --- | --- |
| Valid reviewers | 0 / 2 |
| Reviewer types | none completed |
| Overlap | 0 |
| Overlapping decisive | 0 / 20 |
| Gold accepts | 0 / 8 |
| Gold rejects | 0 / 8 |
| Ambiguous/unfrozen cases | 25 |
| Raw agreement | N/A |
| Cohen's kappa | N/A |
| Per-question/category agreement | N/A |
| Third-party adjudications | 0 |
| Gold hash | N/A |

No provisional gold file was emitted. The freeze command writes gold only after the
Gate passes, and an existing different gold file cannot be overwritten. The
optional audit key is opened only after both reviewer artifacts validate; it never
enters a task, prompt, human package or disagreement packet.

## 5. Real runtime

Real runtime was not implemented or run. The independent Gate requires two distinct
human/provider reviewers, at least 20 overlapping decisive cases, at least 8 accepts
and 8 rejects, raw agreement at least 0.80, kappa at least 0.60 and unresolved
ambiguity no more than 30%. Current reviewer/overlap counts are 0/0, so the explicit
reason is `BLOCK_REAL_REPLAY`.

Consequently themes, styles, ticks, providers, models, Agent tokens/latencies,
Critic coverage, typed-ledger valid rate and real trace completeness are all N/A.

## 6. Typed candidate

No Phase 11 typed evaluation was run. The only available values remain the Phase 9
synthetic, co-designed fixture results:

| Layer | Coverage | Abstain | Precision | Recall | FPR | FNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Synthetic unreviewed/provisional | 22/25 (88%) | 3/25 (12%) | 1.000 | 1.000 | 0.000 | 0.000 |
| Real reviewed | N/A | N/A | N/A | N/A | N/A | N/A |
| Combined reviewed | N/A | N/A | N/A | N/A | N/A | N/A |

The synthetic covered-case values are not promoted. Standalone abstain-aware hard
error recall remains 9/12 = 0.75; the three typed-invalid cases stay unresolved and
fall back to existing rejection only in the offline comparison.

## 7. Production behavior

Production decision changes: none. `STATE_GUARD_TYPED_DECISION_ENABLE` remains
unimplemented/disabled, and no offline typed result is imported by Narrator,
NarrativeStateGuard or Orchestrator. There is no behavior candidate to roll back.

## 8. CanonicalFact consumer

```text
implemented: no
enabled: no
default: disabled/absent
measured gain: N/A
measured regression: N/A
retained or reverted: not implemented
```

No CanonicalFact path can override StatePatch, promote rumor/belief/unknown, inject
Narrator context or treat a missing sidecar as an error.

## 9. Worst cases

1. **Reviewer task format failure:** a recorded test returned one valid and one
   schema-invalid result in a two-case task. The valid case was atomically retained;
   only the invalid case was retried. This validates isolation but is not a real
   reviewer failure sample.
2. **Reviewer disagreement:** unavailable because no human/model reviewer pair has
   completed overlapping cases. Kappa cannot be inferred from unit-test vectors.
3. **Real hard contradiction:** unavailable because real replay is Gate-blocked.
   Phase 9 synthetic negatives are not relabeled as real evidence.
4. **Real probable false positive:** unavailable. The provisional synthetic
   “一起跌进门内” case has still not received independent review.
5. **Typed abstain:** `phase9-hn-holder-wrong-type` remains an invalid-ledger
   abstention; conditional covered-case metrics conceal it.
6. **Repair fact change:** Phase 9's map-handoff deletion remains a provisional
   captured reject without Phase 11 independent confirmation.
7. **CanonicalFact no gain/regression:** no consumer or real denominator exists, so
   both are unmeasured.

## 10. Modified files

### Final net changes

- `scripts/state_guard_review_workflow.py` — task/index schemas, atomic utilities,
  human packages, partial merging, agreement/Gold Gate and real-replay guard.
- `scripts/run_blind_state_guard_review.py` — sharded CLI, synthetic probe,
  checkpoint/resume, local retry, recorded transport and budget enforcement.
- `scripts/export_state_guard_human_review.py` — Markdown/CSV/JSON package export.
- `scripts/import_state_guard_human_review.py` — human import and partial merge CLI.
- `scripts/freeze_state_guard_gold.py` — disagreement export, Gate and immutable gold.
- `backend/tests/test_state_guard_phase11_review.py` — 23 Phase 11 regression cases.

### Review artifacts

- `docs/iter/state_guard_review_tasks/phase11-human-a/` — 25 pending task files,
  index and label-blind packet reference.
- `docs/iter/state_guard_human_review/phase11-human-a/`
- `docs/iter/state_guard_human_review/phase11-human-b/`
- `docs/iter/PHASE11_PLAN.md`
- `docs/iter/PHASE11_STATUS.md`
- `docs/iter/iteration-31-sharded-review-20260721.md`
- `docs/iter/iteration-32-resumable-review-runner-20260721.md`
- `docs/iter/iteration-33-human-review-package-20260721.md`
- `docs/iter/iteration-34-partial-review-import-20260721.md`
- `docs/iter/iteration-35-gold-freeze-20260721.md`

### Real artifacts and reverted candidates

None. Iterations 36–40 were not executed; no candidate was applied or reverted.
`old/` was not modified. Untracked `.tmp/` and user-owned
`scripts/openai_compatible_chat.py` were not staged or changed.

## 11. Reproduction

Generate stable tasks and the two human packages without provider calls:

```powershell
python scripts/run_blind_state_guard_review.py `
  --packet docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  --template docs/iter/state_guard_adjudication/phase9-review-template-v1.json `
  --reviewer-id phase11-human-a `
  --reviewer-type human `
  --batch-size 1 `
  --shuffle-seed 31 `
  --checkpoint-dir docs/iter/state_guard_review_tasks/phase11-human-a `
  --prepare-only

python scripts/export_state_guard_human_review.py `
  docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  --reviewer-id phase11-human-a --shuffle-seed 31 `
  --out-dir docs/iter/state_guard_human_review/phase11-human-a

python scripts/export_state_guard_human_review.py `
  docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  --reviewer-id phase11-human-b --shuffle-seed 32 `
  --out-dir docs/iter/state_guard_human_review/phase11-human-b
```

After two humans independently fill their own `review.csv`, import and merge them:

```powershell
python scripts/import_state_guard_human_review.py import `
  docs/iter/state_guard_human_review/phase11-human-a `
  --input docs/iter/state_guard_human_review/phase11-human-a/review.csv `
  --out-part reviewer-a-part.json

python scripts/import_state_guard_human_review.py merge `
  docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  reviewer-a-part.json `
  --out-review reviewer-a-merged.json `
  --out-coverage reviewer-a-coverage.json

python scripts/import_state_guard_human_review.py import `
  docs/iter/state_guard_human_review/phase11-human-b `
  --input docs/iter/state_guard_human_review/phase11-human-b/review.csv `
  --out-part reviewer-b-part.json

python scripts/import_state_guard_human_review.py merge `
  docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  reviewer-b-part.json `
  --out-review reviewer-b-merged.json `
  --out-coverage reviewer-b-coverage.json

python scripts/freeze_state_guard_gold.py `
  docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  reviewer-a-merged.json reviewer-b-merged.json `
  --audit-key docs/iter/state_guard_adjudication/phase9-blind-key-v1.json `
  --out-report phase11-adjudication-report.json `
  --out-disagreement phase11-disagreement-packet.json `
  --out-gold phase11-gold-labels-v1.json
```

The audit-key command must only be run after both reviewer files are complete and
hash-valid. If the Gate fails, no gold file is written; only the report and blind
disagreement packet are retained.

Validation commands:

```powershell
ruff check scripts/state_guard_review_workflow.py `
  scripts/run_blind_state_guard_review.py `
  scripts/export_state_guard_human_review.py `
  scripts/import_state_guard_human_review.py `
  scripts/freeze_state_guard_gold.py `
  backend/tests/test_state_guard_phase11_review.py

python -m pytest backend/tests/test_state_guard_phase11_review.py `
  backend/tests/test_state_guard_adjudication.py -q

python -m pytest backend/tests/ -q

Push-Location frontend
npm run build
Pop-Location
```

Observed: Ruff passed; focused tests `36 passed`; backend `1342 passed` with one
existing Starlette/httpx deprecation warning; Vite 6.4.1 production build passed.

## 12. Final conclusion

`INCONCLUSIVE：独立审查、预算、provider 或真实样本仍不足。`

The immediate next action is for two independent humans to fill the separate A/B
packages. It is not to authorize a model, implement real replay or modify
StateGuard.
