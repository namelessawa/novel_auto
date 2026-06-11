# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-stage1-v15-15tick.json` (13 narrations)
- source v16: `docs/iter/bench-stage1-v16-15tick.json` (12 narrations)
- paired: 12 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `v16_promote`
- reason: v16 win-rate 70.00% ≥ 45% — meets §4 promote bar
- v16_win_rate: 0.7
- v16_lose_rate: 0.3
- tie_rate: 0.0
- parse_err: 0
- provisional: True

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.894 | 0.8622 |
| distinct char-4 (mean) | 0.9955 | 0.9947 |
| overlap consec char-2 | 0.0866 | 0.1121 |
| tier_hit_rate | 0.8462 | 0.9167 |
| narrations | 13 | 12 |

## Pairwise samples (first 5)

- pair#0: winner=x swap=True reason=段B情节推进更紧凑，角色反应更生动。
- pair#1: winner=x swap=False reason=情节推进明确，角色决策驱动强。
- pair#2: winner=y swap=True reason=情节连贯，角色细腻，推进有力
- pair#3: winner=y swap=True reason=环境压迫感强，角色内心突出，情节紧张。
- pair#4: winner=y swap=True reason=情节推进更清晰，环境连贯性更强。
