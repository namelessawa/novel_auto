# Phase 9 typed StateGuard candidate evaluation

- Runtime integration: disabled
- CanonicalFact consumer: disabled
- Combined dataset: 98 total / 59 decisive / 39 ambiguous
- Typed coverage: 22/25 (0.880)
- Abstain: 3/25 (0.120)

## Reject-positive metrics

| Decision path | Precision | Recall | FPR | FNR | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 0.923 | 1.000 | 0.077 | 0.000 | 0.960 |
| Typed covered cases | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 |
| Typed + baseline fallback | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 |

Conditional metrics exclude abstentions. Standalone abstain-aware hard-error recall is 0.750.

## Behavior gate

Decision: `BLOCK_BEHAVIOR_CANDIDATE`

- independently_reviewed_decisive_cases gate failed: 0 < 20

Iterations 23–25 remain blocked. No production decision, feature flag or CanonicalFact consumer was added.

Report SHA-256: `1c9ed43b18dc2cadcf1c406bd0e82db8f8464daf3809b6bbb1b77209210992d7`
