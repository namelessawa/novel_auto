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
