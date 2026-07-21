# Phase 7 final verdict — fact chain, long context and pressure-style stability

Date: 2026-07-21  
Branch: `codex/longtext-style-iteration-20260721`  
Behavioral baseline: `6477f61b3ade9f3e984f66f457521976106edac9`  
Phase 7 start: `8cb645be1f9713c085e5ef722ae91c55b75eed77`  
Measured candidate: `040ad05`

## 1. Executive summary

This phase solved a concrete infrastructure problem: facts can now be projected to
an atomic, versioned CanonicalFact sidecar with stable identity, source references,
validity, supersession, objective/belief separation and `known_by`. Projection is
delayed until the accepted Tick persistence boundary, is non-fatal, adds no LLM
call, and can be reconciled read-only against four legacy/current views.

It did **not** establish a long-text or style-quality improvement. Two complete
seven-style pressure runs retained only 10/28 narrative ticks each. The comparable
prior-three-style subset retained 4/12 and 3/12, below both the Phase 7 continuation
target (8/12) and the historical 6/12 result. Complete sequence acceptance was 0/7
in both runs. Gate C, 200-Tick and 500-Tick runs were therefore not started.

The experiment also found two measurement gaps:

1. `validate_styles.py` calls Narrator directly and does not exercise Orchestrator
   or CanonicalFact persistence. New artifacts now state this boundary explicitly.
2. StateGuard's model-reported safety and fail-closed evidence result often disagree.
   The samples contain both genuine unfulfilled endpoints and probable evidence/
   ledger ambiguity, so globally relaxing the guard would be unsafe without a
   labeled calibration set.

## 2. Baseline and final measurements

| Item | Baseline / environment | Final evidence |
| --- | --- | --- |
| Python | 3.11.15 | unchanged |
| Node / npm | 24.11.0 / 11.14.1 | unchanged |
| Model | `glm-5.2` through coding provider config | no fallback used |
| Credentials | presence only; no value recorded | no secret committed |
| Backend tests | 1224 passed, 1 existing warning | 1254 passed, 1 same warning |
| Frontend | production build PASS | PASS; 55 modules, JS 320.55 kB / gzip 95.20 kB |
| Historical 4-Tick subset | 6/12 retained | run 1: 4/12; run 2: 3/12 |
| Full Phase 7 Gate B | not previously run | 10/28 retained in both runs |
| Complete style sequences | historical 3-style sample: 0/3 | 0/7 in both runs |
| Repairs | not in comparable cost artifact | 20 attempted / 2 adopted / 18 rejected per run |
| Generation cost | prior artifact lacked current telemetry | 1,193,920 tokens; 298 calls |
| Blind judge cost | separate historical sample | 66,490 tokens |
| Total measured model usage | — | 1,260,410 tokens |
| Wall time | historical 3-style sequence: 2,213 s | 5,922.069 measured generation seconds |

The historical blind Top-1 6/12 and Top-3 7/12 result used 12 separate compatible
and pressure samples. Phase 7 blind runs classified one aggregate retained sequence
per style: Top-1 1/7 then 1/6 and Top-3 3/7 then 2/6. These units differ; only the
two Phase 7 blind runs are directly comparable.

CanonicalFact deterministic evidence:

- 15/15 initial fact-chain counterexamples passed.
- 64/64 focused projection/reconciliation/Orchestrator regressions passed before the
  full suite.
- Active objective facts require authoritative sources; rumor/belief cannot replace
  objective current state; unchanged observations merge provenance rather than
  fabricate supersession.
- Mock full-chain Orchestrator test proves `canonical_facts.json` is persisted after
  accepted state changes. No real-model style sample exercised that path.

## 3. Iteration record

### Iteration 07 — ACCEPT (infrastructure)

Hypothesis: a stable source-aware fact identity layer can expose supersession and
knowledge provenance without becoming a generation consumer. Added CanonicalFact
model/store and 15 counterexamples. No Prompt, consumer or LLM cost changed.

### Iteration 08 — ACCEPT (infrastructure/measurement)

Hypothesis: typed projection after accepted state transitions plus read-only
reconciliation can establish the source chain without changing narrative behavior.
Added Event/World/Character/StatePatch/continuity/OpenLoop projection, Orchestrator
persistence wiring, reconciliation CLI and full-chain tests. No new LLM call or
prompt token was introduced.

### Iteration 09 — REJECT as quality continuation evidence

Hypothesis: a write-only sidecar candidate should preserve the historical retention
floor in two repeated pressure runs. Both runs instead accepted 0/7 sequences and
retained only 4/12 and 3/12 in the prior subset. Because the style benchmark bypasses
Orchestrator, the result cannot be attributed to the sidecar; it documents the
existing Narrator/StateGuard baseline and a benchmark execution-path blind spot.

The small accepted measurement change labels future style artifacts as
`execution_path=narrator_direct`, `orchestrator_exercised=false`, and
`canonical_fact_sidecar_exercised=false`. It has a regression test and no generation
or cost effect.

## 4. Final comparison

| Metric | Run 1 | Run 2 | Verdict |
| --- | ---: | ---: | --- |
| Retained ticks | 10/28 | 10/28 | stable but too low |
| Prior 3-style subset | 4/12 | 3/12 | fails >= 8/12 gate |
| Accepted complete sequences | 0/7 | 0/7 | fail |
| Repair adoption | 2/20 | 2/20 | 10% |
| Retry rejection | 18 | 18 | systemic |
| Tokens | 614,357 | 579,563 | expensive |
| Calls | 152 | 146 | expensive |
| Blind Top-1 | 1/7 | 1/6 | weak |
| Blind Top-3 | 3/7 | 2/6 | weak |

Verifier and repair used 770,412 generation tokens (64.53%) while only four of forty
repairs were adopted. The side-by-side artifact is
`phase7-gateb-sidecar-compare-20260721.md`.

No Baseline-vs-final prose pair is claimed as a quality improvement: there was no
accepted behavioral candidate, the sidecar is not consumed by Narrator, and the two
real-model runs expose large output variance (for example, `literary` retained 2/4
then 0/4).

## 5. Worst cases

### Case A — likely evidence false negative, run 2 literary tick 1

- Required: map remains with the protagonist; protagonist and injured companion both
  cross the exit; the old exit is sealed.
- Final verifier reason: all actions completed and state was consistent.
- Evidence excerpt: `林雪把地图塞进怀里`.
- Trigger: `复合终态没有逐字证明两名参与者都越过边界`.
- Outcome: rejected after the second repair; aggregate literary prose became empty.
- Risk: accepting the reason blindly would weaken evidence discipline, but rejecting
  without participant-resolving evidence loses an otherwise possibly valid scene.

### Case B — genuine endpoint failure, run 1 literary tick 4

- Required: gatekeeper proposes map-for-entry; map is delivered; both enter the city;
  negotiation creates a new explicit cost.
- Excerpts: `“地图换入城。”守门人说` and `她拉下拉链，把地图抽出来，递过去。`
- Actual ending: the pair entered a rooftop watchtower still inside the outer
  fortification; the gatekeeper ordered them to leave the territory before dawn.
- Trigger: rooftop watchtower is not the required city interior.
- Outcome: correctly rejected; this case prevents a global “trust reported_safe” fix.

### Case C — incomplete ledger location, run 2 noir tick 4

- Required: both enter the city after handing over the map and accepting a new cost.
- Prose/verifier reason said all requirements were fulfilled.
- Declared locations included one explicit city-interior value and another value
  equivalent to `由林雪架着`, which describes support rather than a location.
- Trigger: deterministic location matcher found only 1/2 participants inside.
- Outcome: rejected after retry. This may be correct fail-closed behavior, but it
  shows continuity ledgers need typed per-character locations rather than prose-like
  placeholders.

Additional reproducibility failure: run 2 bootstrap requested A/B/C cast counts
1/1/1 but returned 1/1/0. The run was retained rather than silently rerun.

## 6. Risks and unresolved gaps

- **Overfitting:** all new real-model evidence is one apocalypse theme and one
  four-event pressure sequence. No claim generalizes to healing, historical,
  espionage, science-fiction or low-intensity themes.
- **Judge bias:** the same model family performed generation, verification/repair and
  style judgment on this configured path. Blind labels were hidden, but correlated
  model behavior remains.
- **StateGuard tradeoff:** evidence completeness and prose retention conflict. The
  current data cannot safely choose a global threshold.
- **Benchmark coverage:** style validation bypasses Orchestrator and the sidecar. A
  cheap full-runtime deterministic replay fixture is needed before another costly
  matrix.
- **Randomness:** provider sampling seed is not exposed by the style CLI. Commands and
  inputs match, but byte-for-byte seed replay is not demonstrated.
- **Cost:** actual two-run generation was about 1.19M tokens, above the earlier
  0.55M–0.85M estimate. Another candidate matrix was not authorized by evidence.
- **Long range:** no cross-seed 30–50 Tick Gate C, 200 Tick Gate D, 500 Tick Gate E or
  D1–D8 drift analysis was run because Gate B failed.
- **Context work:** SummaryTree L0–L3 injection and NarrativeContextBundle were not
  implemented; the prerequisite fact-consumer gate did not pass.
- **Compatibility:** no migration or production-default change exists. Old novels
  continue to use persisted style snapshots. Sidecar absence remains valid for old
  data.

## 7. Modified files

Runtime/measurement code:

- `backend/narrative/canonical_facts.py` — CanonicalFact model, status transitions,
  stable IDs and atomic store.
- `backend/narrative/canonical_projection.py` — typed accepted-state projection.
- `backend/narrative/canonical_reconciliation.py` — four-view read-only comparison.
- `backend/agents/orchestrator.py` — delayed, non-fatal projection at persistence.
- `backend/tick_runtime.py` — sidecar lifecycle.
- `scripts/reconcile_canonical_facts.py` — read-only reconciliation CLI.
- `scripts/validate_styles.py` — explicit direct-Narrator execution metadata.

Tests:

- `backend/tests/test_canonical_facts.py`
- `backend/tests/test_canonical_projection.py`
- `backend/tests/test_canonical_reconciliation.py`
- `backend/tests/test_orchestrator_p0.py`
- `backend/tests/test_validate_styles_script.py`

Records/artifacts:

- `docs/iter/PHASE7_PLAN.md`, `PHASE7_STATUS.md`
- `docs/iter/iteration-07-canonical-fact-sidecar-20260721.md`
- `docs/iter/iteration-08-sidecar-projection-reconciliation-20260721.md`
- `docs/iter/iteration-09-gateb-measurement-20260721.md`
- `docs/iter/phase7-gateb-sidecar-compare-20260721.md`
- two raw generation JSON/Markdown pairs and two blind-judge JSON/Markdown pairs
- this final verdict

No file was deleted. `old/` was untouched. The unrelated untracked
`scripts/openai_compatible_chat.py` was not read, modified or committed.

## 8. Reproduction commands

```powershell
python -m pytest backend/tests/ -q

Push-Location frontend
npm run build
Pop-Location

python scripts/validate_styles.py `
  --provider-file coding.txt `
  --mode pressure `
  --pressure-theme apocalypse_wasteland `
  --styles literary,first_person_immersive,ensemble_epic,warm_healing,philosophical_meditative,noir_cold,rough_grit_realism `
  --ticks 4 `
  --sequence `
  --max-revisions 0 `
  --out docs/iter/phase7-gateb-sidecar-run1-glm-20260721.json

# Repeat the same command with run2 output for the independent repeat.
python scripts/classify_styles_blind.py `
  --input docs/iter/phase7-gateb-sidecar-run1-glm-20260721.json `
  --provider-file coding.txt `
  --sample-styles all `
  --judge-budget 50000 `
  --out docs/iter/phase7-gateb-sidecar-run1-blind-glm-20260721.json

python scripts/reconcile_canonical_facts.py --help
```

Do not use `compare_bench.py` for these `validate_styles` artifacts; its schema is
different and it reports misleading zeros. Use the committed Phase 7 comparison.

## 9. Final conclusion

`INCONCLUSIVE：受配额、模型或测量限制，证据不足。`

The deterministic CanonicalFact foundation is locally valid and reversible, but
there is insufficient cross-theme, cross-seed, long-range or end-to-end runtime
evidence to adopt it as a production consumer or claim improved novel quality.
