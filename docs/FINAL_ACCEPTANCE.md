# Final acceptance

Run the unified acceptance command from the repository root:

```powershell
python scripts/run_final_acceptance.py --resume
```

`--resume` may reuse a green offline receipt only when the complete non-ignored
source tree has the same SHA-256. It never skips a failed hard Gate, changes a
seed, resumes P7/P8 after P6 failure, or authorizes another real-provider run.

## Gate result

| Gate | Result | Evidence |
| --- | --- | --- |
| P0 | PASS | isolated branch/worktree and frozen baseline |
| P1 | PASS | deterministic Planner, one Writer, no full Retry |
| P2 | PASS | Recorded 100/100, semantic recall 7/7, liveness 0 |
| P3 | PASS | frozen 24+6 Repair replays and full revalidation |
| P4 | PASS | recovery/API/UI/export and warning-free regression |
| P5 | PASS | complete offline suite and Recorded 100/100 |
| P6 | FAIL | historical seed failed after two repair rounds |
| P7 | NOT RUN | strict prerequisite P6 failed |
| P8 | NOT RUN | strict prerequisite P6 failed |
| P9 | PASS when final runner receipt is green | reports, hashes, scan and recovery |

## P6 evidence

The historical `action_conflict` seed was run with all five fixed styles, three
sections per style, desired length 900, checkpoint every section and runtime
rebuild every two sections. Every run used process-only `coding.txt`
configuration, `glm-5.2`, no Planner call, no full Retry and no combo retry.

1. Initial attempt: provider returned invalid Writer JSON before a candidate.
   The failure was frozen; GLM structured acceptance now disables thinking and
   records that configuration.
2. First repair round: literary completed 2/3. Section 3 was ten characters
   short; Repair added an unauthorized approximate count. The true rejection
   was frozen. A narrow audited removal preserves the number Validator.
3. Second/final repair round: section 1 was 656 characters. Required event and
   end state both completed, but the only expansion patch referenced a missing
   anchor. Full revalidation rejected it. The two-round limit was exhausted.

No P6 attempt committed a hard fact error, state conflict, illegal ThreadChange,
evidenceless StateDelta, revision jump, duplicate or half commit.

## Offline hard Gate

The final runner executes and records:

```text
python -m pytest backend/tests/ -q -W error
python -m ruff check backend scripts
python -m compileall -q backend scripts
npm --prefix frontend run test:author
npm --prefix frontend run build
npm --prefix frontend audit --omit=dev
git diff --check
```

It then scans tracked files and all local evidence for the exact API key and
base URL from the original `coding.txt`, without persisting either value.

Outputs are under `.tmp/final-goal-20260728/`:

- `manifest.json`
- `report.json` and `report.md`
- `artifact-sha256.json`
- `secret-scan.json`
- `run-state.json`
- `recovery.md`

The authoritative verdict for this execution is
`NOVEL_AUTO_FINAL_FAIL`.
