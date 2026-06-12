# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-stage5-seed3-50tick.json` (46 narrations)
- source v16: `docs/iter/bench-iter103-seed3-50tick.json` (44 narrations)
- paired: 44 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `v16_promote`
- reason: v16 win-rate 80.00% ≥ 45% — meets §4 promote bar
- v16_win_rate: 0.8
- v16_lose_rate: 0.2
- tie_rate: 0.0
- parse_err: 0
- provisional: False

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.8545 | 0.868 |
| distinct char-4 (mean) | 0.9903 | 0.9903 |
| overlap consec char-2 | 0.1112 | 0.1 |
| tier_hit_rate | 0.8478 | 0.7955 |
| narrations | 46 | 44 |

## Pairwise samples (first 5)

- pair#0: winner=y swap=True reason=段A角色内心刻画深，情节推进强。
- pair#1: winner=y swap=True reason=情节推进连贯，角色反应生动。
- pair#2: winner=x swap=False reason=环境描写细腻，角色行动连贯，情节推进自然。
- pair#3: winner=y swap=False reason=情节推进更紧凑，角色解谜推动故事发展。
- pair#4: winner=y swap=True reason=段A氛围连贯，角色声音细腻。
