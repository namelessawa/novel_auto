# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-v15-final-iter29.json` (2 narrations)
- source v16: `docs/iter/bench-v16-final-iter31.json` (1 narrations)
- paired: 1 (truncated to min)
- judge_calls: 1 (budget 15000)
- judge_tokens_estimated: 5000

## Verdict

- **label**: `v16_promote`
- reason: v16 win-rate 100.00% ≥ 45% — meets §4 promote bar
- v16_win_rate: 1.0
- v16_lose_rate: 0.0
- tie_rate: 0.0
- parse_err: 0
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

- pair#0: winner=y swap=True reason=情节推进紧张，角色声音鲜明。
