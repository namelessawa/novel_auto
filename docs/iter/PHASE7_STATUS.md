# Phase 7 status

Updated: 2026-07-21

## Current state

- Branch: `codex/longtext-style-iteration-20260721`
- Behavioral baseline: `6477f61b3ade9f3e984f66f457521976106edac9`
- Phase 7 starting HEAD: `8cb645be1f9713c085e5ef722ae91c55b75eed77`
- Measurement candidate: `040ad05`
- Status: `STOPPED — Gate B failed twice; Gate C/D/E not entered`
- Final conclusion: `INCONCLUSIVE`; do not change production defaults.

## Accepted locally

- Iteration 07: versioned atomic CanonicalFact sidecar with stable identity,
  provenance, validity, `known_by`, objective/belief separation and supersession.
- Iteration 08: typed projection at the accepted persistence boundary and read-only
  reconciliation against TickState, legacy FactLedger, KnowledgeGraph and continuity.
- Iteration 09 measurement fix: `validate_styles` now labels its direct-Narrator
  execution boundary and cannot silently claim Orchestrator/sidecar coverage.
- Final Gate A: backend `1254 passed, 1 warning`; frontend production build PASS.

## Gate B result

- Two `glm-5.2` runs, each 7 styles × 4 pressure ticks, same registered theme,
  same command and zero section-level revisions.
- Both runs retained 10/28 ticks and accepted 0/7 complete sequences.
- Prior three-style subset retained 4/12 then 3/12; continuation required >= 8/12.
- Both runs: 20 repair attempts, 2 adopted, 18 rejected.
- Generation cost: 1,193,920 tokens; blind judge: 66,490; total 1,260,410.
- Blind aggregate-sequence results: Top-1 1/7 then 1/6; Top-3 3/7 then 2/6.
- The second blind run has six samples because all `literary` ticks were rejected.
- `reported_safe=true` coexisted with non-empty conflict lists in 17/28 initial
  verifications in both runs. Cases include both real event failures and strict
  evidence/ledger ambiguity; a global threshold reduction is unsafe.
- One run reported a bootstrap cast mismatch (requested A/B/C=1/1/1, actual
  1/1/0), retained as a reproducibility risk.

## Measurement boundary

`validate_styles.py` instantiates `NarratorAgent` directly. None of the 14 sample
directories contains `canonical_facts.json`. The real-model runs therefore measure
the Narrator/StateGuard/style path, not the Orchestrator sidecar persistence path.
The sidecar's zero-behavior property is supported by deterministic/full-chain mock
tests only, not a real-model end-to-end benchmark.

## Gate status

| Gate | Status | Evidence |
| --- | --- | --- |
| A | PASS | 1254 backend tests; frontend build PASS |
| B | FAIL | 0/7 accepted twice; 4/12 and 3/12 prior-subset retention |
| C | NOT RUN | Gate B continuation condition failed |
| D | NOT RUN | no accepted production consumer/default change |
| E | NOT RUN | no production-default proposal; prerequisites failed |

## Safety and worktree

- No API key or credential value was read into reports, printed, or committed.
- `coding.txt` is recorded only as the provider source; the model and credential
  presence are non-secret metadata.
- `scripts/openai_compatible_chat.py` remains unrelated, untracked, unread,
  unmodified and uncommitted.
- No push, PR, deploy, production-data change or migration was performed.
