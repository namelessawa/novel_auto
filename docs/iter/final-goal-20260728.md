# Novel Auto final goal execution log

This log executes the 2026-07-28 final-goal report in strict P0–P9 order.
The source report was read completely and has SHA-256
`AFE4C8C7DC5470D532B1390A82166DE541ADDF222C2E47514BADF1C578966DDA`.

## Immutable execution baseline

- Base HEAD: `b87371a3dad3a885615e3bab490a39a15f39b410`
- Source branch: `codex/writer-planning-mode-20260727`
- Work branch: `codex/novel-auto-final-goal-20260728`
- Remote source ref: exact match (`0/0` ahead/behind)
- Isolation: a separate clean worktree; the original dirty worktree is read-only
- Main branch: not checked out, modified, or merged
- Provider configuration: process-only values loaded from the original
  `coding.txt`; credential values are never copied into artifacts

## P0 — baseline, isolation, and recoverability

Status: **PASS**

The baseline is fully recorded and known failures are separated from new
failures. A missing ignored config in the new worktree initially prevented test
collection; after a credential-free ignored config was supplied and
`coding.txt` was loaded into process environment, the comparable baseline was:

| Check | Actual result |
| --- | --- |
| Backend tests | 1 failed, 1550 passed, 1 warning |
| Author UI | 14 passed, 0 failed |
| Frontend production build | passed |
| Ruff | 59 errors, 2 invalid-noqa warnings |
| Python compileall | passed |
| npm production audit | 0 vulnerabilities |
| git diff --check | passed |

Frozen baseline failures:

- Cross-platform source hashing failure in
  `test_calibration_artifact_is_reproducible_and_source_hashed`; the existing
  regression expects an LF fixture hash while the Windows worktree supplies
  CRLF. The fixture and expected values remain unchanged.
- Ruff reports 59 pre-existing issues.
- Python tests emit the known Starlette/httpx deprecation warning.

P0 explicitly does not require a green baseline, but requires complete,
non-hidden evidence. All three defects must be closed before their later hard
Gates.

## User-owned files

The original worktree still contains exactly the protected top-level state:

- modified `docs/iter/style-generation-samples-glm52-20260722.md`
- untracked `.tmp/`, `.vite/`, and `scripts/openai_compatible_chat.py`
- ignored `.env`, `config.json`, and `coding.txt`

The `.tmp` tree has 3825 files with inventory fingerprint
`04529E9A1F36277CCE0B047D31B095CA0512E3D413ECEC0840236BADD1AAE028`;
the `.vite` tree has one file with fingerprint
`570384032625A84FFC1D65ACB84B45EFE47BDC8AF9BF63D4A6BA837AD18A0A39`.
None is in the work branch index.

Local resumable state is under `.tmp/final-goal-20260728/`.

## Next Gate

P1 only: collapse the default runtime to deterministic planning, one Writer
call, and at most one targeted Repair while preserving validators and legacy
read compatibility.

## P1 — runtime-chain simplification

Status: **PASS**

The formal generation path now builds `ChapterPlan` deterministically from the
frozen `EventExecutionPlan` and `SectionBudgetPlan`. `AuthorWriter.plan()` is
reachable only when `AUTHOR_LLM_PLANNER_EXPERIMENTAL` is explicitly true; the
flag defaults false and unrecognized values fail closed. The ChapterPlan schema,
deterministic validator, diagnostics, and persisted transaction fields remain
available.

The complete Writer Retry provider path and prompt were removed. A transaction
can now perform exactly one initial Writer call and at most one bounded Repair
Patch call. Old transactions containing `writer_retry_count`,
`writer_retry_performed`, and `retry_tokens` remain readable.

Per-segment character counts remain valid ChapterPlan diagnostics, but the
Writer prompt now treats them as soft structural guidance. Only the total
`SectionBudgetPlan` range remains a hard length Gate.

Verification:

- P1 targeted planning, retry-removal, transaction, recovery, ChapterPlan, and
  revision-guard tests: 42 passed.
- Full backend regression: 1555 passed, 1 failed, 1 warning. The only failure is
  the exact P0-frozen cross-platform calibration hash test; new failures: 0.
- Changed-file Ruff: passed.
- Changed-file compileall and `git diff --check`: passed.
- Validator files modified: 0.

Next Gate: P2, auditable semantic memory and StoryThread liveness.

## P2 — auditable semantic memory and StoryThread liveness

Status: **PASS**

Every generation now persists a frozen `ContextManifest` containing Bible and
Canonical revisions, NarrativeContract and deterministic execution-spec hashes,
actual active thread IDs, selected memory IDs, per-memory selection reasons and
matched entities/threads, discarded candidates and reasons, per-slot
character/token budgets, global utilization, and truncation state.

Memory selection is deterministic and fail-closed:

- only `confirmed` memories at or before the frozen Canonical revision may enter;
- machine-checkable canonical claims discard conflicting memories;
- superseded, uncertain, future, irrelevant, and rank-limited memories retain an
  auditable discard record;
- section summaries carry entity/thread provenance but never override
  CanonicalState.

Seven semantic-recall probes cover character knowledge boundaries,
relationships, item ownership/state, location rules, open promises, main-thread
clues, and superseded facts. A probe passes only when the correct memory is
selected, its required semantics appear in prose, forbidden old facts do not,
and final CanonicalState still satisfies the frozen claims. Selecting an ID
without using its semantics is a regression failure.

Active StoryThreads now have deterministic open/advance/resolve conditions,
revision windows, last-progress revision, deadlines, and an explicit pause
field. On the third section without progress, due threads are inserted into the
frozen SectionGoal and EventExecutionPlan. The authority validator requires
matching prose evidence and an advance/resolve proposal; opening an unrelated
thread cannot satisfy this Gate. Successful changes atomically update
`last_advanced_revision`, and every transaction records its liveness decision.

Formal evidence:

- P2 regression set: 56 passed, 0 failed.
- Recorded long-range: 100/100 atomically committed after a 50-section
  checkpoint and process resume.
- Runtime rebuilds: 18; resume count: 1.
- Staged recovery and stale StoryBible rejection: passed.
- Semantic recall: 7/7; wrong-version memory uses: 0.
- Knowledge, relationship, item, location, and time conflicts: 0.
- Revision jumps, duplicate sections, duplicate transactions, half commits: 0.
- Main-thread liveness window violations: 0.
- Context token p95/max: 8414/8414 against the 12000-token hard limit.
- Planner provider calls: 0; full Writer Retry calls: 0.
- Changed-file Ruff, compileall, and `git diff --check`: passed.

Machine-readable evidence:
`.tmp/final-goal-20260728/p2/recorded-100-final/report.json`, SHA-256
`EBC29D38FA4E9AC048B1AF8BAF51D6D0116220252B0A9436E0866216E55800F9`.
All thirteen P2 Gate checks in that artifact are `true`.

Next Gate: P3, Writer first-pass quality, bounded Repair quality, and frozen
quality fixtures.

## P3 — Writer first-pass input and one bounded Repair

Status: **PASS**

The Writer prompt now carries each event and required end state once. The
NarrativeContract slot retains authority-only facts and constraints, while the
deterministic EventExecutionPlan is the sole Writer-facing event/end-state
inventory. The duplicated SectionWritingPlan and SectionBudgetPlan JSON copies
were removed from that slot; the server-owned final directive remains the sole
four-segment budget and stop-condition instruction. The full plans remain
frozen in the transaction and execution-spec hash.

For the common 900–1100 acceptance range, `SectionBudgetPlanBuilder` keeps the
center target at 1000. All five style contracts state that style cannot change
facts; noir explicitly cannot be short, classical cannot add history, and
hot-blooded cannot add injuries, casualties, enemies, or background.

Preflight issues are now typed entries in `RepairPlan` and are exposed to the
single Patch prompt with their code, message, and details. This does not restore
full Writer Retry: an initial Writer candidate still gets at most one bounded
Patch call followed by complete Narrative, authority, length, ending, balance,
regression, revision, and atomic-commit revalidation.

The Patch schema and validator continue to support missing/incomplete events,
wrong actor/target/end state, unsupported-fact deletion, bounded expansion, and
server-selected compaction. They continue to reject whole-section replacement,
unlisted content, proposal/title/summary/memory mutation, and regressions.

Formal evidence:

- Frozen historical failures: 24/24 recovered; 17/17 attempted Repairs
  succeeded; regression 0; bad commit 0.
- Frozen final real rejects: 6/6; Patch failure 0; Validator failure 0;
  regression 0.
- P3 regression set: 66 passed, 0 failed.
- Historical weakness coverage includes noir/classical under-length,
  hot-blooded unsafe expansion, `POST_RESOLUTION_EXPANSION`,
  `REQUIRED_EVENT_INCOMPLETE`, and `END_STATE_WRONG_HOLDER`.
- New real-provider failures in P3: 0; therefore new-failure fixture coverage is
  100% without changing either frozen fixture.
- Changed-file Ruff, compileall, and `git diff --check`: passed.
- Validator thresholds modified: 0; full Writer Retry calls: 0.

Machine-readable evidence:
`.tmp/final-goal-20260728/p3/gate.json`, SHA-256
`BC400019A6FCFB9803A400AE59FAB18B6177B6BD97B940303812B2CB0AD77A7D`.
The replay artifacts have SHA-256
`B2F77BE1D37C5FD52F860E5EF4678DF807BD2C3D50A96D81276F928CA2E38159`
and
`871DC3F50003F8938C8F1726C8AFE437F4246237C04FB94FC6992AA0291EC81B`.

Next Gate: P4, product API/UI/export/audit UX and closure of the P0 baseline
defects required by later hard Gates.
