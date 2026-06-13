# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-iter144-seed1-cast221-sideline.json` (46 narrations)
- source v16: `docs/iter/bench-iter153-seed1-cast221-budget1200.json` (43 narrations)
- paired: 43 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `v16_promote`
- reason: v16 win-rate 50.00% ≥ 45% — meets §4 promote bar
- v16_win_rate: 0.5
- v16_lose_rate: 0.3
- tie_rate: 0.2
- parse_err: 0
- provisional: False

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.8563 | 0.8851 |
| distinct char-4 (mean) | 0.9898 | 0.9943 |
| overlap consec char-2 | 0.1 | 0.0762 |
| tier_hit_rate | 0.8043 | 0.6977 |
| narrations | 46 | 43 |

## Pairwise samples (first 5)

- pair#0: winner=tie swap=True reason=两者连贯、角色鲜明、情节推进自然。
- pair#1: winner=y swap=False reason=情节推进更紧迫，角色声音突出
- pair#2: winner=y swap=False reason=段B情节紧凑，动作感强，推进更快。
- pair#3: winner=y swap=True reason=动作连贯，情节推进强，角色紧张感突出。
- pair#4: winner=x swap=False reason=段A氛围营造更好，角色内心描写细腻，情节推进连贯。
