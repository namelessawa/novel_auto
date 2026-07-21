# Phase 9 verdict — StateGuard ground truth and typed consumer

Date: 2026-07-21

```text
branch: codex/longtext-style-iteration-20260721
phase9_start: a66eb80c7e413439dddf23eea48180059a4cccd4
phase9_evidence_head: 26c97accaa21a270ec89e0e258f250b63f50fb4a
python: 3.11.15
node: v24.11.0
npm: 11.14.1
real_provider_calls: 0
production_behavior_changes: 0
```

## 1. Executive summary

### Infrastructure

Phase 9 added a versioned, complete `state-guard-trace-v1` bound to actual
TickRuntime/Orchestrator replay. It preserves the original Narrator draft, typed/raw
ledger, complete verifier and repair rounds, deterministic checks, Critic provenance,
location/knowledge context, CanonicalFact before/after and final decision. It also
added full-runtime suites for 12 hard negatives and 13 expected accepts, a blind
adjudication export/import workflow, and an offline typed decision candidate.

### Measurement

The combined calibration inventory grew from 73 to 98 cases. Decisive cases grew
from 34 to 59; signal-backed decisive accepts/rejects grew from 20/0 to 33/12;
ambiguous rate fell from 53.4% to 39.8% without relabeling any missing Phase 7
draft. All 25 new decisive cases carry complete actual StateGuard traces.

The typed candidate covers 22/25 cases (88%) and abstains on three invalid typed
ledgers (12%). On covered cases its reject-positive precision/recall/FPR/FNR are
1.0/1.0/0.0/0.0. With abstentions conservatively falling back to the current Guard,
the same metrics are 1.0/1.0/0.0/0.0 versus baseline
0.923/1.0/0.077/0.0. These are synthetic, co-designed fixture results, not real
novel-quality evidence.

### Behavior

No production decision path changed. The offline candidate is not imported by
Narrator, NarrativeStateGuard or Orchestrator. No typed feature flag, CanonicalFact
consumer, real replay mode, provider change, threshold relaxation or regex expansion
was added. The behavior gate is `BLOCK_BEHAVIOR_CANDIDATE` because independently
reviewed decisive cases remain 0/20. Iterations 23–25 were not executed.

### Quality

All 12 complete hard negatives remain rejected under the fallback-preserving path;
all three repair-fact-change cases remain rejected. The offline candidate resolves
one captured probable false positive (“Alice和Bob一起跌进门内”) without accepting a
hard negative. The result is provisional because there is no independent reviewer
and no real-provider replay.

## 2. Dataset

| Metric | Phase 8 baseline | Phase 9 final |
| --- | ---: | ---: |
| Total cases | 73 | 98 |
| Decisive | 34 | 59 |
| Ambiguous | 39 | 39 |
| Ambiguous rate | 53.4% | 39.8% |
| Signal-backed decisive accept | 20 | 33 |
| Signal-backed decisive reject | 0 | 12 |
| Typed candidate covered | 0 | 22/25 |
| Independently human-reviewed decisive | 0 | 0 |

Source inventory:

- synthetic minimal/source cases: 42 (17 Phase 8 + 25 Phase 9);
- Phase 7 recorded-source cases: 56;
- complete Phase 9 full-runtime fixture traces: 25;
- real-provider cases: 0;
- independently human-reviewed cases: 0;
- independent-model-reviewed cases: 0;
- pre-existing project-agent rubric-reviewed cases: 73, provisional only.

The 25 Phase 9 cases are synthetic responses transported through the actual runtime
and StateGuard control flow. “Recorded mode” describes fixture transport; it does
not mean a provider was called.

Hard-negative categories with at least three decisive cases: 9 — endpoint,
location, holder, condition, knowledge, ungrounded fact, wrong ledger type, missing
ledger field and repair fact change. Evidence extraction failure and reasonable
omission each have multiple complete expected-accept cases.

## 3. Trace completeness

Across one Iteration 18 trace, 12 hard-negative traces and 13 expected-accept traces:

| Payload | Complete |
| --- | ---: |
| Original draft | 26/26 |
| Declared typed/raw/legacy ledger | 26/26 |
| Verifier input + raw + normalized output | 26/26 |
| Repair full text (required or explicitly not required) | 26/26 |
| Deterministic evidence checks | 26/26 |
| Required end states | 26/26 |
| Location context | 26/26 |
| Critic payload (required or explicit skip) | 26/26 |

Repair was actually required in 13 cases and full repair prose is present in 13/13.
Critic executed in one fixture and its input/output is complete; other traces carry
an explicit skip reason. CanonicalFact before/after arrays are bound into every
runtime trace even when the before array is empty.

Evidence hashes:

- complete trace replay:
  `df2eff9b179a49beac285e0f5735c9cc2cd33203d81c2b7b39f933e579df5646`;
- hard-negative suite:
  `3f30f1626356d6e9197f89d0caf901f934dced9433ce882aca2c3fbc2fd9b6b8`;
- probable-false-positive suite:
  `6aef1bf2d5fb50d14b81d630913a1d2ff7446a8cb9116651599f8bfec14ce191`;
- blind reviewer packet:
  `fe80127aa1c46313b92e0d47c9e2fa776612df462bd3fbb89e09bdb6eda33ef5`;
- typed evaluation report:
  `1c9ed43b18dc2cadcf1c406bd0e82db8f8464daf3809b6bbb1b77209210992d7`.

## 4. Typed candidate

Positive class is reject.

| Decision path | Coverage | Abstain | Precision | Recall | FPR | FNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Existing Guard baseline | 25/25 | 0% | 0.923 | 1.000 | 0.077 | 0.000 |
| Typed candidate, covered only | 22/25 | 12% | 1.000 | 1.000 | 0.000 | 0.000 |
| Typed + baseline fallback | 25/25 | 0% | 1.000 | 1.000 | 0.000 | 0.000 |

- Coverage: 88%, Wilson 95% `[0.700442, 0.958332]`.
- Abstain: 12%, Wilson 95% `[0.041668, 0.299558]`.
- Covered precision/recall Wilson 95%: `[0.700855, 1.0]`.
- Standalone abstain-aware hard-error recall: 9/12 = 0.75, Wilson 95%
  `[0.467695, 0.911058]`.

The standalone recall is reported because conditional metrics can hide unresolved
hard negatives. The three abstentions are invalid typed-ledger cases; none becomes
an acceptance. A future integration would have to retain baseline decisions on
abstain, but no such integration was made.

The offline candidate's evidence order is required endpoints, authoritative typed
pre-state, declared typed end-state, prose, structured verifier fields, then summary
reason. It does not use CanonicalFact or fixture labels. The verifier summary cannot
override a typed/prose conflict.

## 5. Behavior candidate

No production behavior candidate was implemented because the independent-review
gate failed. Consequently production decision changes are empty.

For audit, the offline fallback-preserving comparison has exactly one decision
change:

| Case | Baseline | Offline fallback path | Evidence |
| --- | --- | --- | --- |
| `phase9-fp-synonym-fall-inside` | reject | accept | both typed locations are `city_gate_inner`; prose says both actors “一起跌进门内” |

The three typed abstentions fall back to baseline reject and therefore are not
decision changes. This comparison is not enabled in production.

## 6. CanonicalFact consumer

- Enabled: no.
- Default value: no setting or consumer was added.
- Measured gain: N/A.
- Measured regression: N/A.
- Retained: trace capture and existing Phase 8 sidecars only; no new consumer.

Iteration 24 required a passing behavior gate. Because independent review is 0/20,
StateGuard does not read CanonicalFact through a new path and Narrator receives no
CanonicalFact injection.

## 7. Real runtime

Not run. Iteration 25 was behind the same gate and was stopped before provider work.
No `--mode real`, budget/resume implementation, real generation, real judge or model
switch was attempted. This prevents synthetic fixture evidence from being described
as real quality improvement.

## 8. Cost

| Cost source | Value |
| --- | ---: |
| Fixture transport calls | 209 |
| Provider calls | 0 |
| Real generation calls | 0 |
| Real judge calls | 0 |
| Critic-exercised fixture cases | 1 |
| Accepted fixture prose | 447 characters |
| Model tokens by Agent | N/A |
| Critic/verifier/repair model tokens | N/A |
| Judge tokens | N/A |
| Tokens per accepted 1000 characters | N/A |

Fixture telemetry carries zero token counters for deterministic replay, but this is
not reported as zero-cost model inference: fixture model tokens are N/A.

## 9. Iteration record

| Iteration | Hypothesis and minimal change | Result | Decision |
| --- | --- | --- | --- |
| 18 | Complete versioned trace removes payload-loss blindness | 1 full runtime trace; all completeness fields present | `ACCEPT_MEASUREMENT` |
| 19 | 12 actual Guard hard negatives establish reject denominator | 12/12 reject; 3 verifier + 2 repair rounds each | `ACCEPT_MEASUREMENT` |
| 20 | 13 complete expected accepts expose false rejection and lower ambiguity | 12 baseline accepts, 1 captured false reject; 39.8% ambiguity | `ACCEPT_MEASUREMENT` |
| 21 | Separate blind packet/key enables independent review without label leakage | 25 opaque, shuffled cases; import/kappa tested; 0 real reviewers | `ACCEPT_INFRASTRUCTURE` |
| 22 | Offline typed evidence can cover most complete cases safely | 88% coverage, 12% abstain, 0 hard negatives accepted | `ACCEPT_MEASUREMENT` |

Iteration 20 had intermediate fixture passes with missing repair fallback and wording
that conflicted with production preflight. Those artifacts were overwritten only
after the fixture issues were recorded; no Guard threshold or regex changed. No
behavior candidate was accepted or rolled back because the behavior gate was never
opened.

## 10. Worst cases

1. Hard contradiction — `phase9-hn-location-outer-fort`: required
   `city_gate_inner`; prose stops in the outer fort with the inner gate shut and the
   ledger remains outer. Baseline and typed candidate reject.
2. Probable false positive — `phase9-fp-synonym-fall-inside`: typed endpoints and
   prose agree, but the current deterministic phrase matcher rejects “跌进”. The
   offline candidate accepts; no independent reviewer has confirmed the label.
3. Typed abstain — `phase9-hn-holder-wrong-type`: the declared holder field cannot
   be typed, so the candidate abstains and preserves baseline reject. Conditional
   recall alone would hide this unresolved case.
4. Repair fact change — `phase9-hn-repair-deletes-handoff`: original prose gives the
   map to Bob; repair deletes the handoff and returns holder to Alice. Complete repair
   evidence is captured and rejected.
5. Reviewer disagreement — unavailable. There are zero completed independent
   reviews, so no real disagreement example or kappa can be reported. The importer's
   disagreement math is unit-tested, but test vectors are not evidence. This missing
   case is the explicit behavior-gate blocker.

## 11. Risks

- Overfitting: all 25 new decisive cases are synthetic and share one small runtime
  world; category counts do not demonstrate cross-theme generalization.
- Reviewer bias: fixture authors supplied provisional expected labels; no human or
  independent-model review has been frozen against the blind packet.
- Verifier coupling: synthetic verifier responses and candidate rules are evaluated
  on co-designed traces, so 1.0 covered metrics are optimistic.
- Coverage: the Wilson intervals are wide; three invalid typed ledgers abstain and
  standalone hard-error recall is only 0.75 when abstentions count as unresolved.
- Real-model variance: provider latency, token cost, Critic behavior and prose
  variability are unmeasured.
- Compatibility: trace capture is additive, but its JSON volume is larger. No data
  migration was performed.
- CanonicalFact: no consumer gain or regression evidence exists, so enabling one
  remains unsafe.

## 12. Modified files

### Final net code changes

- `backend/agents/narrative_critic.py` — retain Critic before/after text per round.
- `backend/agents/narrative_state_guard.py` — capture complete verifier/repair and
  deterministic decision evidence.
- `backend/agents/narrator_agent.py` — pass original draft, typed/raw ledgers and
  bounded location/knowledge context into the trace.
- `backend/narrative/state_guard_trace.py` — strict versioned trace schema.
- `backend/narrative/state_guard_typed_candidate.py` — offline-only typed candidate.
- `scripts/replay_runtime_sequence.py` — full Guard suite replay and trace binding.
- `scripts/build_phase9_guard_fixtures.py` — reproducible Phase 9 fixture builder.
- `scripts/export_state_guard_adjudication.py` — blind packet/key export.
- `scripts/import_state_guard_adjudication.py` — review validation and agreement.
- `scripts/evaluate_state_guard_typed_candidate.py` — coverage/confusion/Gate report.

### Regression tests and fixtures

- `backend/tests/test_runtime_replay.py`
- `backend/tests/test_state_guard_trace_capture.py`
- `backend/tests/test_phase9_guard_replay_suite.py`
- `backend/tests/test_state_guard_adjudication.py`
- `backend/tests/test_state_guard_typed_candidate.py`
- `backend/tests/fixtures/runtime_replay/phase9_hard_negative_suite_v1.json`
- `backend/tests/fixtures/runtime_replay/phase9_probable_fp_suite_v1.json`

### Iteration records and artifacts

- `docs/iter/PHASE9_PLAN.md`
- `docs/iter/PHASE9_STATUS.md`
- `docs/iter/iteration-18-full-guard-trace-20260721.md`
- `docs/iter/iteration-19-hard-negative-replay-20260721.md`
- `docs/iter/iteration-20-probable-fp-replay-20260721.md`
- `docs/iter/iteration-21-blind-adjudication-20260721.md`
- `docs/iter/iteration-22-typed-candidate-20260721.md`
- `docs/iter/phase9-guard-trace-recorded-20260721.json`
- `docs/iter/phase9-hard-negative-replay-20260721.json`
- `docs/iter/phase9-probable-fp-replay-20260721.json`
- `docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json`
- `docs/iter/state_guard_adjudication/phase9-blind-key-v1.json`
- `docs/iter/state_guard_adjudication/phase9-review-template-v1.json`
- `docs/iter/state_guard_typed_candidate/phase9-typed-candidate-v1.json`
- `docs/iter/state_guard_typed_candidate/phase9-typed-candidate-v1.md`
- `docs/iter/verdict-20260721-phase9-guard-groundtruth-consumer.md`

Deleted files: none. Reverted behavior candidates: none; none was authorized by the
Gate. `old/` was not modified.

The untracked `scripts/openai_compatible_chat.py` is pre-existing user-owned work and
was never read, modified or staged. `.tmp/phase9-iter18` is an untracked local replay
work directory; a policy-blocked cleanup attempt left it outside all commits.

## 13. Validation and reproduction

Final validation:

```powershell
python -m pytest backend/tests/ -q

Push-Location frontend
npm run build
Pop-Location
```

Observed:

```text
1309 passed, 1 existing Starlette/httpx deprecation warning
Vite 6.4.1: 55 modules transformed; production build passed
```

Rebuild fixtures and full-runtime replay reports without provider calls:

```powershell
python scripts/build_phase9_guard_fixtures.py

$phase9Run = Join-Path $env:TEMP ("novel-auto-phase9-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $phase9Run | Out-Null

python scripts/replay_runtime_sequence.py `
  backend/tests/fixtures/runtime_replay/phase9_hard_negative_suite_v1.json `
  --mode recorded `
  --work-dir (Join-Path $phase9Run "hard") `
  --out (Join-Path $phase9Run "hard.json") `
  --max-calls 20

python scripts/replay_runtime_sequence.py `
  backend/tests/fixtures/runtime_replay/phase9_probable_fp_suite_v1.json `
  --mode recorded `
  --work-dir (Join-Path $phase9Run "positive") `
  --out (Join-Path $phase9Run "positive.json") `
  --max-calls 20
```

Rebuild the checked-in blind packet and typed evaluation:

```powershell
python scripts/export_state_guard_adjudication.py `
  docs/iter/phase9-hard-negative-replay-20260721.json `
  docs/iter/phase9-probable-fp-replay-20260721.json `
  --out-packet docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  --out-key docs/iter/state_guard_adjudication/phase9-blind-key-v1.json `
  --out-template docs/iter/state_guard_adjudication/phase9-review-template-v1.json

python scripts/evaluate_state_guard_typed_candidate.py `
  --phase8-dataset docs/iter/state_guard_calibration/phase8-state-guard-calibration-v1.json `
  --phase8-report docs/iter/state_guard_calibration/phase8-state-guard-calibration-report-v1.json `
  docs/iter/phase9-hard-negative-replay-20260721.json `
  docs/iter/phase9-probable-fp-replay-20260721.json `
  --out-json docs/iter/state_guard_typed_candidate/phase9-typed-candidate-v1.json `
  --out-md docs/iter/state_guard_typed_candidate/phase9-typed-candidate-v1.md
```

After independent reviewers complete separate copies of the review template, import
them without exposing the key beforehand:

```powershell
python scripts/import_state_guard_adjudication.py `
  docs/iter/state_guard_adjudication/phase9-blind-packet-v1.json `
  docs/iter/state_guard_adjudication/phase9-blind-key-v1.json `
  reviewer-a.json reviewer-b.json `
  --out-json phase9-adjudication-report.json `
  --out-md phase9-adjudication-report.md
```

## 14. Final conclusion

`CONDITIONAL PASS：校准基础有效，但人工裁决、真实运行或 hard-negative 证据仍不足以修改生产默认。`

The immediate blocker is independent review (0/20), followed by real-provider and
cross-theme evidence. The correct next step is to distribute the blind packet and
freeze at least 20 independent human decisive labels; it is not to modify the Guard.
