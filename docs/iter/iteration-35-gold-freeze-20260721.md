# Iteration 35 — independent Gold Gate and immutable freeze

```text
Iteration: 35
Evidence gap:
There are no completed human reviews, but the future Gate must support partial
overlap, per-question agreement, disagreement-only adjudication and immutable gold.

Hypothesis:
A Gate over two hash-bound merged reviews can compute overlap/agreement/kappa and
freeze gold only after every threshold passes.

Single primary change:
Add partial-review adjudication, disagreement packet export, stable gold hash,
no-overwrite freeze and a hard-contradiction acceptance veto.

Provider calls allowed: no
Authorized budget: 0
Expected benefit: reproducible Gate when real human results arrive
Safety risk: provisional/disputed labels are frozen or project-agent fixtures count
Validation: stable hash under reviewer order, overwrite refusal, evidence-mode Gate,
hard-contradiction veto and blocked real-replay helper
Rollback condition: non-independent evidence passes or failed Gate freezes gold
```

## Result

- Tests use synthetic reviewer vectors only; they prove math/control flow, not gold.
- Project-agent and mock/recorded evidence cannot enter the independent Gate.
- Gold output is written only when the Gate passes and cannot be silently replaced.
- Current valid reviewers/overlap/accepts/rejects: 0 / 0 / 0 / 0.
- Agreement / kappa / gold hash: unavailable / unavailable / unavailable.
- Provider calls / known tokens / uncertain upper bound: 0 / 0 / 0.
- Decision: `INCONCLUSIVE`.
- Gate: `BLOCK_REAL_REPLAY`.
- Rollback: no behavior candidate exists.
