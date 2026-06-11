# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-v15-final-iter29.json` (2 narrations)
- source v16: `docs/iter/bench-v16-final-iter31.json` (1 narrations)
- paired: 1 (truncated to min)
- judge_calls: 1 (budget 30000)
- judge_tokens_estimated: 5000

## Verdict

- **label**: `indeterminate`
- reason: no valid pairwise samples
- v16_win_rate: n/a
- v16_lose_rate: n/a
- tie_rate: n/a
- parse_err: n/a
- provisional: True

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.8589 | 0.9448 |
| distinct char-4 (mean) | 0.9931 | 0.9976 |
| overlap consec char-2 | 0.0947 | 0.0 |
| tier_hit_rate | 1.0 | 1.0 |
| narrations | 2 | 1 |

## Pairwise samples (first 5)

- pair#0: winner=parse_error swap=True reason=json_parse_failed
