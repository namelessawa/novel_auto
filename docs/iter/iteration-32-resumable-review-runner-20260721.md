# Iteration 32 — resumable per-case reviewer runner

```text
Iteration: 32
Evidence gap:
The whole-packet runner cannot retain valid siblings, resume per case, probe provider
capabilities without blind material, or separate historical and newly authorized
budgets.

Hypothesis:
Atomic case checkpoints, a synthetic probe and one case-local format retry can make
review execution recoverable without broad retries.

Single primary change:
Extend the runner with checkpoint/resume, local schema validation, per-case result
files, isolated failure artifacts, recorded transport and conservative budget state.

Provider calls allowed: no
Authorized budget: 0
Expected benefit: completed cases never repeat; invalid cases do not erase siblings
Safety risk: retry leakage, hidden provider calls or unknown usage counted as zero
Validation: mock/recorded callbacks, probe inspection, zero-budget call spy and bounds
Rollback condition: any unauthorized call, repeated complete case or unbounded retry
```

## Result

- Empty final content becomes `provider_failed` for the current task.
- Malformed output retries only the failed case; valid siblings remain complete.
- Each case receives at most one format repair retry, then `needs_human_review`.
- Resume validates completed hashes and never calls a completed case again.
- Probe messages contain no blind case ID or prose.
- Unknown provider calls add configured input + output to the conservative bound.
- At 70% the warning is set; at 85% no new case is opened.
- With Phase 11 budget zero, provider call count remains zero and exit code is 3.
- Decision: `ACCEPT_INFRASTRUCTURE`.
- Rollback: not required.
