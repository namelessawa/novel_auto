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
