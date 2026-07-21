# Phase 10 verdict — independent adjudication and real StateGuard Gate

Date: 2026-07-21

```text
branch: codex/longtext-style-iteration-20260721
phase10_start: 8b6b0eb69d5e76838e07a58779d306c3ec4e075f
infrastructure_commit: 6170106
review_evidence_commit: 017bd6643470af20095ddebf6ecb7b510a650c97
blind_packet_sha256: 2b28c5c9a11dc04e6971268054bc7296c88a6ff5a1b079105ec7880a09abc4da
production_behavior_changes: 0
real_provider_replay_cases: 0
valid_independent_reviews: 0
```

## 1. Executive summary

### Infrastructure

Phase 10 strengthened the blind export/import boundary and added an isolated,
budgeted OpenAI-compatible review runner. The packet now asks the six required fact
questions and exposes prose plus repair attempts without exposing fixture class,
verifier decision, baseline/candidate decision or expected label. Reviews are bound
to packet hash, reviewer identity, model family/name, timestamps, prompt hash,
temperature, input files and blind-key non-access attestation. Invalid output,
provider failure and future provider-reported budget overrun retain atomic failure
checkpoints.

### Measurement

Four isolated reviewer directories were produced from the same 25-case packet. Six
provider requests yielded five model responses but no complete importable review.
Known exact model usage is 26,147 tokens; the known lower bound excluding one
unknown first call exceeds 31,547; the conservative total upper bound is 62,140
against the fixed 60,000 reviewer budget. Independent decisive, accept and reject
counts are therefore 0/0/0. Agreement and Cohen's kappa are not computable.

### Behavior

No StateGuard decision, typed feature flag, threshold, regex, CanonicalFact consumer,
Narrator input, SummaryTree integration or runtime default changed. The mandatory
review Gate returns `BLOCK_REAL_REPLAY`. Iterations 24–30 were not executed, and no
real replay implementation or production candidate was introduced.

### Quality

Phase 10 establishes a stricter, reproducible review boundary but supplies no valid
new quality label. Phase 9's 88% offline typed coverage and perfect covered-case
metrics remain synthetic and provisional. No claim of real-novel quality,
cross-theme gain or production false-positive reduction is supported.

## 2. Independent adjudication

| Measure | Result |
| --- | --- |
| Valid reviewer count | 0 |
| Reviewer types attempted | independent models only |
| Model families attempted | Zhipu/GLM, Xiaomi/MiMo, DeepSeek |
| Full cases required per review | 25 |
| Raw agreement | N/A |
| Cohen's kappa | N/A |
| Third-party adjudications | 0; no valid first pair existed |
| Gold decisive accepts | 0 |
| Gold decisive rejects | 0 |
| Remaining ambiguous/unfrozen | 25 |
| Gate | `BLOCK_REAL_REPLAY` |

The project agent was not counted as a reviewer. Reviewer copies contained only
`packet.json` and `template.json` before calls. The blind key was never supplied to
an API. Because no two valid reviews existed, generating a disagreement packet or
gold labels would fabricate evidence; neither artifact was produced.

The Gate requires at least 20 independently reviewed decisive cases, including at
least 8 accepts and 8 rejects. Observed values are 0/0/0, so Iteration 24 cannot be
accepted as measurement.

## 3. Real runtime

| Field | Result |
| --- | --- |
| Themes / styles / ticks | none |
| Provider / model | none for replay |
| Replay calls / tokens | 0 / N/A |
| Latency | N/A |
| Critic coverage | N/A |
| Typed-ledger valid rate | N/A |
| Trace completeness | N/A |

Real replay was intentionally not implemented or run. It was downstream of the
independent-review Gate, so doing so after the Gate failed would violate the ordered
experiment and spend from the separate 250,000-token runtime budget without usable
gold labels.

## 4. Typed candidate

No Phase 10 typed evaluation was performed. The following values are carried from
Phase 9 and are explicitly synthetic, co-designed fixture measurements:

| Layer | Coverage | Abstain | Precision | Recall | FPR | FNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Synthetic covered cases | 22/25 (88%) | 3/25 (12%) | 1.000 | 1.000 | 0.000 | 0.000 |
| Real reviewed cases | N/A | N/A | N/A | N/A | N/A | N/A |
| Combined reviewed cases | N/A | N/A | N/A | N/A | N/A | N/A |

- Coverage Wilson 95%: `[0.700442, 0.958332]`.
- Abstain Wilson 95%: `[0.041668, 0.299558]`.
- Covered precision/recall Wilson 95%: `[0.700855, 1.0]`.
- Standalone abstain-aware hard-error recall: 9/12 = 0.75, Wilson 95%
  `[0.467695, 0.911058]`.

These values were not promoted because the reviewed synthetic, reviewed real and
combined denominators are all zero in Phase 10.

## 5. Production behavior candidate

There is no production candidate and the decision-change list is empty. The one
Phase 9 offline comparison (`phase9-fp-synonym-fall-inside`, reject to accept) was
not independently confirmed and remains disconnected from production. No rollback
was needed because no behavior candidate was applied.

## 6. CanonicalFact consumer

```text
enabled: no
default value: no new flag or consumer exists
measured gain: N/A
measured regression: N/A
retained or reverted: not implemented
```

CanonicalFact cannot override authoritative StatePatch, and no path was added that
could promote rumor, belief or `unknown` into an objective fact.

## 7. Cost

| Mode / attempt | Model | Input | Output | Total or bound | Known latency | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Reviewer A expanded | glm-5.2 | N/A | N/A | ≤24,178 | about 73 s | malformed JSON before checkpoint |
| Reviewer A catalog | glm-5.2 | 5,892 | 3,500 | 9,392 | 44.21 s | empty final content |
| Reviewer B catalog | mimo-v2.5-pro | 0 | 0 | 0 | N/A | authentication rejected before model |
| Reviewer C catalog | glm-5.2 | 5,892 | 2,500 | 8,392 | 50.38 s | empty final content |
| Reviewer D catalog | deepseek-v4-pro | 6,562 | 1,801 | 8,363 | 34.24 s | empty final content |
| Reviewer C compact, thinking disabled | glm-5.2 | N/A | N/A | >5,400 and ≤11,815 | N/A | per-reviewer budget exceeded before old checkpoint |
| Real generation / Critic / Guard replay | none | N/A | N/A | N/A | N/A | Gate-blocked |

Provider requests/model responses/valid reviews were 6/5/0. Exact known tokens are
26,147. The conservative cumulative upper bound is 62,140, so no additional model
call was made. Failed-call uncertainty is not represented as zero usage.

## 8. Worst cases

1. **Reviewer disagreement:** unavailable. No valid pair exists, so reporting a
   disagreement rate or kappa would be fabricated. This is itself the primary
   measurement failure.
2. **Real hard contradiction:** unavailable because real replay was Gate-blocked.
   The Phase 9 synthetic `phase9-hn-location-outer-fort` remains rejected but is not
   substituted for real evidence.
3. **Real probable false positive:** unavailable. The synthetic “一起跌进门内” case
   remains a provisional offline false positive with no independent confirmation.
4. **Typed abstain:** `phase9-hn-holder-wrong-type` cannot form a legal typed holder;
   the offline candidate abstains and preserves baseline reject. Conditional metrics
   hide this unresolved hard negative.
5. **Repair fact change:** `phase9-hn-repair-deletes-handoff` removes the map handoff
   and returns the holder to Alice; Phase 9 captures and rejects it, but Phase 10 did
   not independently revalidate the label.
6. **CanonicalFact no gain/regression:** no consumer exists, so both gain and
   regression are unmeasured. Enabling it would be unsupported.
7. **Provider stability:** GLM returned malformed or empty final content across
   multiple prompt sizes; DeepSeek and GLM spent reasoning/output budget without a
   usable 25-case decision object; MiMo credentials were rejected.

## 9. Modified files

### Final net changes

- `scripts/export_state_guard_adjudication.py` — six-question packet, visible repair
  evidence, raw-ledger fallback, hash-bound v2 review metadata and isolated copies.
- `scripts/import_state_guard_adjudication.py` — strict metadata/coverage/identity
  validation, agreement/kappa, blind disagreement export, third-review merge and
  behavior Gate.
- `scripts/run_blind_state_guard_review.py` — secret-safe isolated runner, compact
  lossless prompt, compact response normalization, strict budgets and atomic failure
  checkpoints.
- `backend/tests/test_state_guard_adjudication.py` — 13 leak, hash, identity,
  coverage, disagreement, compact-prompt and budget-checkpoint regressions.

### Reverted behavior candidates

None. StateGuard, typed behavior and CanonicalFact production paths were never
changed.

### Review artifacts

- `docs/iter/PHASE10_PLAN.md`
- `docs/iter/PHASE10_STATUS.md`
- `docs/iter/iteration-23-independent-review-20260721.md`
- `docs/iter/state_guard_adjudication/phase9-blind-{packet,key}-v1.json`
- `docs/iter/state_guard_adjudication/phase9-review-template-v1.json`
- `docs/iter/state_guard_adjudication/phase10-reviewer-{a,b,c,d}/`
- `docs/iter/state_guard_adjudication/phase10-review-attempt-summary.json`

### Real runtime artifacts

None. Iterations 25–30 were not executed. Deleted files: none. `old/` was not
modified. Untracked user-owned `scripts/openai_compatible_chat.py` and `.tmp/` were
not read, modified or staged during this Phase 10 work.

## 10. Reproduction

Local validation and blind-packet regeneration:

```powershell
python -m pytest backend/tests/test_state_guard_adjudication.py -q
python -m pytest backend/tests/ -q

Push-Location frontend
npm run build
Pop-Location

python scripts/export_state_guard_adjudication.py `
  docs/iter/phase9-hard-negative-replay-20260721.json `
  docs/iter/phase9-probable-fp-replay-20260721.json `
  --out-packet docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  --out-key docs/iter/state_guard_adjudication/phase9-blind-key-v1.json `
  --out-template docs/iter/state_guard_adjudication/phase9-review-template-v1.json

python scripts/run_blind_state_guard_review.py --help
python scripts/import_state_guard_adjudication.py --help
```

Observed final validation:

```text
focused adjudication tests: 13 passed
backend: 1319 passed, 1 existing Starlette/httpx deprecation warning
frontend: Vite 6.4.1, 55 modules transformed, production build passed
```

Import is only valid after two independent complete reviews exist:

```powershell
python scripts/import_state_guard_adjudication.py `
  docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  docs/iter/state_guard_adjudication/phase9-blind-key-v1.json `
  reviewer-a.json reviewer-b.json `
  --out-json docs/iter/state_guard_adjudication/phase10-adjudication-report.json `
  --out-md docs/iter/state_guard_adjudication/phase10-adjudication-report.md `
  --out-disagreement-packet docs/iter/state_guard_adjudication/phase10-disagreement-packet.json `
  --out-gold docs/iter/state_guard_adjudication/phase10-gold-labels-v1.json
```

That command was not run with fabricated reviewer files. Provider-review commands
are intentionally not presented as a rerun instruction: the fixed review budget has
already reached its conservative upper bound. A future attempt requires a renewed
explicit budget and valid credentials, while still withholding the blind key.

## 11. Final conclusion

`INCONCLUSIVE：审查、真实样本、模型稳定性或预算不足。`

The retained result is infrastructure and failure evidence only. It does not
authorize real replay, a StateGuard production default, typed behavior, CanonicalFact
consumption or the next long-text context phase.
