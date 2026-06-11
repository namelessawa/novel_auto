# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-stage1-v15-15tick.json` (13 narrations)
- source v16: `docs/iter/bench-stage2-gated-15tick.json` (13 narrations)
- paired: 13 (truncated to min)
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
| distinct char-2 (mean) | 0.894 | 0.919 |
| distinct char-4 (mean) | 0.9955 | 0.9959 |
| overlap consec char-2 | 0.0866 | 0.0726 |
| tier_hit_rate | 0.8462 | 0.6154 |
| narrations | 13 | 13 |

## Pairwise samples (first 5)

- pair#0: winner=y swap=False reason=情节更紧凑，悬念强，推动故事发展。
- pair#1: winner=y swap=False reason=情节推进更紧凑，悬念感强。
- pair#2: winner=y swap=False reason=段B情节推进更强，角色行动更突出。
- pair#3: winner=x swap=True reason=段B情节推进更完整，角色声音更生动。
- pair#4: winner=y swap=True reason=情节紧凑，角色行动直接有力，推进迅速
