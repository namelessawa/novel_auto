# StateGuard calibration report

- Dataset: `phase8-state-guard-calibration-v1.json`
- Cases: 73 (decisive 34, ambiguous 39 / 0.534)
- Human-reviewed: 0
- Positive class: reject; ambiguous cases are excluded.

## Provisional-label quality metrics

| Signal | Coverage | TP | FP | TN | FN | Precision | Recall | FPR | FNR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| verifier_reported_safe | 0.588 | 0 | 1 | 19 | 0 | 0.000 | — | 0.050 | — |
| deterministic_evidence_gate | 0.588 | 0 | 4 | 16 | 0 | 0.000 | — | 0.200 | — |
| combined_final_decision | 0.588 | 0 | 0 | 20 | 0 | — | — | 0.000 | — |
| typed_ledger_candidate | 0 | — | — | — | — | — | — | — | — |

Undefined values are intentionally not coerced. There is no labeled reject with recorded signals, so hard-error recall cannot be measured.

## Repair

- Attempts: 40
- Success: 4 (0.100)
- Fact preservation: 32 (0.800)

## Behavior gate

Decision: `BLOCK_BEHAVIOR_CANDIDATE`

- only 34 decisive labels; minimum behavior gate is 40
- no labeled reject has recorded verifier/deterministic/combined signals
- no label has independent human review
- typed-ledger candidate decision coverage is zero

Operational reproduction targets recorded production outcomes and is not ground-truth quality evidence.

Report SHA-256: `b4d6f86a0c1b9c12c14ab5d82903317b4763185afd7fde549606c5c0c636dddc`
