# Iteration 09 — Gate B repeat baseline and execution-path measurement

- iteration_id: `20260721-09-gateb-measurement`
- date: `2026-07-21`
- base_git_sha: `2017dcebb1da8849a36493430d042e98ac827618`
- candidate_git_sha: `040ad05`
- provider: `custom` OpenAI-compatible endpoint; credentials present, values not recorded
- model: `glm-5.2`
- themes: `apocalypse_wasteland`
- styles: `literary`, `first_person_immersive`, `ensemble_epic`, `warm_healing`,
  `philosophical_meditative`, `noir_cold`, `rough_grit_realism`
- seeds: registry theme seed reused; no provider sampling-seed CLI is exposed
- tick_counts: 4 per style, 28 per run, two independent runs

## Hypothesis

```text
Observation:
CanonicalFact projection is write-only and should not change Narrator behavior, but
the required seven-style pressure baseline had not been rerun on the Phase 7 SHA.

Root-cause hypothesis:
Two identical-parameter runs should preserve the prior three-style retention floor
while adding zero prompt tokens; any stable quality change would indicate an
unexpected consumer or runtime side effect.

Prepared minimum scope:
No production-code quality change. Run the same registered theme/style contracts and
four-tick sequence twice, then perform blind classification over the retained prose.

Expected improvement:
No behavior change; prior three-style retained >= 8/12 was the continuation gate.

Possible regression:
Lower retention, new fact errors, event omissions, style confusion, or verifier cost
growth. A measurement-path bypass could make the test unable to exercise sidecar.

Validation:
Two complete runs, structured StateGuard traces, known-contract judge, blind Top-1/
Top-3, per-agent tokens and wall time; inspect sample directories for sidecar output.

Rollback/stop condition:
Either run retained <= 6/12 in the prior subset, hard errors/omissions increased,
results were not stable, or another candidate would require material extra spend.
```

## Files and artifacts

- files_changed:
  - `scripts/validate_styles.py`: artifact-only execution profile; explicitly records
    direct Narrator path and that Orchestrator/CanonicalFact were not exercised.
  - `backend/tests/test_validate_styles_script.py`: regression for the execution profile.
  - `docs/iter/phase7-gateb-sidecar-run{1,2}-glm-20260721.{json,md}`: raw generation,
    StateGuard, style and cost traces.
  - `docs/iter/phase7-gateb-sidecar-run{1,2}-blind-glm-20260721.{json,md}`: anonymous
    all-candidate style classifications.
  - `docs/iter/phase7-gateb-sidecar-compare-20260721.md`: schema-correct comparison.
- tests_added: one execution-boundary regression.

## Metrics

- baseline_metrics:
  - historical three-style four-tick retention: 6/12
  - historical blind result: Top-1 6/12, Top-3 7/12, but on a different 12-sample unit
- candidate_metrics:
  - run 1 retention: 10/28; prior subset 4/12
  - run 2 retention: 10/28; prior subset 3/12
  - accepted sequences: 0/7 and 0/7
  - repairs: 20 attempts / 2 adopted / 18 rejected in each run
  - blind: 1/7 Top-1, 3/7 Top-3; then 1/6 Top-1, 2/6 Top-3
  - generation: 1,193,920 tokens, 298 calls, 5,922.069 measured seconds
  - blind judge: 66,490 tokens
- failure_samples: see comparison and final verdict; raw traces retain before/after/
  retry evidence without storing credentials or private user novels.
- cost_delta: actual two-run generation cost was about 1.19M tokens, above the earlier
  0.55M–0.85M estimate; no further real-model candidate was launched.

## Measurement result

All 14 style work directories had `tick_state.json` but no `canonical_facts.json`.
Code inspection confirms `validate_styles.py` directly instantiates `NarratorAgent`.
The benchmark therefore measures the Narrator/StateGuard/style path, not the
Orchestrator persistence boundary. The execution-profile field closes this reporting
blind spot for future artifacts without changing generation behavior or token usage.

## Verdict

- verdict: `REJECT` as Gate B evidence for further production wiring
- rollback_status: no runtime candidate to roll back; CanonicalFact sidecar foundation
  remains accepted, but no StateGuard consumer was added
- next_recommendation: design a cheap deterministic replay or mock/full-runtime
  parity fixture that exercises Orchestrator and sidecar before purchasing another
  seven-style matrix. Separately calibrate StateGuard evidence disagreements with a
  human-labeled true-error/false-positive set; do not lower thresholds globally.
