# Phase 10 plan — independent adjudication, real replay and guarded production candidates

Date: 2026-07-21

Branch: `codex/longtext-style-iteration-20260721`

Starting HEAD: `8b6b0eb69d5e76838e07a58779d306c3ec4e075f`

Behavioral baseline: `6477f61b3ade9f3e984f66f457521976106edac9`

Phase 9 verdict: `CONDITIONAL PASS`

## Evidence carried forward

- Phase 9 provides 25 complete, signal-backed synthetic traces: 12 provisional
  rejects and 13 provisional accepts. These are not independent gold labels.
- The blind packet/key/template are versioned and hash-bound, but no independent
  review has been completed.
- The offline typed candidate covers 22/25 cases and never enters production.
- No real-provider runtime trace, typed production behavior, or CanonicalFact
  StateGuard consumer exists.
- Untracked `scripts/openai_compatible_chat.py` remains user-owned and out of scope.
- Untracked `.tmp/phase9-iter18` remains outside every commit.

## Ordered iterations

1. Iteration 23: strengthen blind material and obtain two isolated independent-model
   review submissions. The hidden key is not supplied to either reviewer.
2. Iteration 24: validate metadata and coverage, compute agreement/kappa, export
   disagreements without prior answers, obtain third-party adjudication if needed,
   and freeze gold labels without overwriting reviews.
3. Gate review. Stop immediately if independent decisive/accept/reject counts,
   agreement, kappa, ambiguity, or taxonomy coverage fail.
4. Iteration 25: only after the review gate, implement a strict-budget real runtime
   mode with checkpoint/resume and secret-safe provider loading.
5. Iterations 26–27: only after real-mode tests, run the bounded cross-theme sample,
   independently review real traces, and report synthetic/real layers separately.
6. Iterations 28–29: only after both reviewed layers pass, consider default-off
   typed behavior and CanonicalFact read-only candidates.

## Reviewer isolation

- Reviewer A: external `glm-5.2` session, temperature 0.
- Reviewer B: external `mimo-v2.5-pro` session, temperature 0.
- Optional adjudicator: external `deepseek-v4-pro` session, only disagreement cases.
- Reviewers receive only their packet/template copies and the fixed rubric prompt.
- Model family, model name, start/end timestamps, prompt hash, packet hash, Token
  usage, and blind-key non-access attestation are retained.
- Independent-model reviews are not called human review.

## Budgets and stop boundary

- Reviewer/judge total budget: 60,000 model tokens.
- Real generation total budget: 250,000 model tokens.
- Real provider calls: at most 100.
- No budget is automatically increased.
- If Iteration 24 fails its Gate, real replay and all behavior iterations stop.
- No push, PR, deploy, migration, production data write, or `old/` modification.
