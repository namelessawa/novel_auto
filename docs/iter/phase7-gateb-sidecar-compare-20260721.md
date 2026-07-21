# Phase 7 Gate B — two-run pressure comparison

This comparison reads the `validate_styles.py` schema directly. The generic
`compare_bench.py` parser is for `bench_tick.py` artifacts and reported zeros for
these files, so its output was discarded rather than treated as evidence.

## Execution boundary

- Git SHA for both generation runs: `2017dcebb1da8849a36493430d042e98ac827618`
- Model: `glm-5.2`
- Theme: `apocalypse_wasteland`
- Styles: `literary`, `first_person_immersive`, `ensemble_epic`, `warm_healing`,
  `philosophical_meditative`, `noir_cold`, `rough_grit_realism`
- Sequence: 4 pressure ticks per style
- Revisions: 0 section-level revisions
- Runtime path: direct `NarratorAgent` over a cloned `TickState`
- Orchestrator exercised: no
- CanonicalFact sidecar exercised: no; none of the 14 sample directories contains
  `canonical_facts.json`
- Provider/model/temperature path was unchanged between runs. The script exposes no
  provider sampling-seed argument, so these are independent repeat runs, not a claim
  of deterministic byte-for-byte replay.

## Aggregate results

| Metric | Run 1 | Run 2 | Decision boundary |
| --- | ---: | ---: | --- |
| Completed style samples | 7/7 | 7/7 | complete |
| Accepted style samples | 0/7 | 0/7 | failed |
| Retained narrative ticks | 10/28 | 10/28 | failed |
| Retained ticks, prior 3-style subset | 4/12 | 3/12 | required >= 8/12 |
| Repair attempts | 20 | 20 | high |
| Repairs adopted | 2 | 2 | 10% |
| Ticks rejected after retry | 18 | 18 | high |
| Generation tokens | 614,357 | 579,563 | 1,193,920 combined |
| LLM calls | 152 | 146 | 298 combined |
| Measured duration | 3,016.176 s | 2,905.893 s | 5,922.069 s combined |
| Known-contract accepted | 0/7 | 0/7 | failed because full sequences were incomplete |
| Blind Top-1 | 1/7 (14.29%) | 1/6 (16.67%) | weak |
| Blind Top-3 | 3/7 (42.86%) | 2/6 (33.33%) | weak |
| Blind judge tokens | 36,061 | 30,429 | 66,490 combined |

Total measured generation plus blind-judge usage was **1,260,410 tokens**. Blind
run 2 has six samples because all four `literary` ticks were rejected and the
classifier correctly skipped empty prose.

The earlier Top-1 `6/12` and Top-3 `7/12` baseline used 12 separate compatible and
pressure samples from `style-baseline-glm-20260721.json`. The present classifier
uses one aggregate sequence per style. The sampling units differ, so the old and new
percentages must not be presented as a direct regression. The two Phase 7 runs are
comparable to each other.

## Retention by style

| Style | Run 1 | Run 2 | Worst run |
| --- | ---: | ---: | ---: |
| literary | 2/4 | 0/4 | 0/4 |
| first_person_immersive | 1/4 | 1/4 | 1/4 |
| ensemble_epic | 1/4 | 2/4 | 1/4 |
| warm_healing | 2/4 | 1/4 | 1/4 |
| philosophical_meditative | 2/4 | 1/4 | 1/4 |
| noir_cold | 1/4 | 3/4 | 1/4 |
| rough_grit_realism | 1/4 | 2/4 | 1/4 |

## Generation-token concentration

| Agent/stage | Combined tokens | Share of generation tokens |
| --- | ---: | ---: |
| narrative_state_verifier | 460,956 | 38.61% |
| narrator | 338,938 | 28.39% |
| narrative_state_repair | 309,456 | 25.92% |
| style sequence/validation judges | 33,879 | 2.84% |
| bootstrap, including regenerated anchors | 50,691 | 4.25% |

Verifier plus repair consumed 770,412 tokens (64.53%) while only 4/40 repair
attempts were adopted.

## Reproducible verifier conflict

The verifier trace separates the model's `reported_safe` from the guard's recomputed
`safe`. This is intentionally fail-closed, but the disagreement was frequent:

| Stage | Run 1 `reported_safe=true` with conflicts | Run 2 |
| --- | ---: | ---: |
| initial verification | 17/28 | 17/28 |
| first repair verification | 15/20 | 13/20 |
| retry verification | 13/19 | 11/19 |

These disagreements include both real failures and evidence-contract failures. They
must not be relabeled wholesale as false positives:

1. Real failure: a sequence required entry into the city, but prose and ledger ended
   inside a rooftop watchtower still outside the requested endpoint.
2. Evidence ambiguity: the reason said both participants crossed a sealed exit, while
   deterministic participant evidence could not prove both actors from the supplied
   quotations.
3. Causal-evidence ambiguity: prose had wet/damaged map language, but the evidence did
   not directly prove rain caused the damage.
4. Ledger incompleteness: one participant's location was `由林雪架着`, so the
   deterministic two-person city-location check matched only one of two actors.

## Gate verdict

`FAIL` for Gate B quality acceptance. Do not enter Gate C, do not wire CanonicalFact
into StateGuard as a production consumer, and do not modify global defaults from
these results. CanonicalFact projection remains accepted as deterministic,
non-consuming infrastructure; real end-to-end sidecar behavior remains unmeasured by
this benchmark path.
