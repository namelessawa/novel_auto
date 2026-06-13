# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-iter124-seed2-cast221.json` (42 narrations)
- source v16: `docs/iter/bench-iter146-seed2-cast221-sideline.json` (43 narrations)
- paired: 42 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `v16_promote`
- reason: v16 win-rate 50.00% ≥ 45% — meets §4 promote bar
- v16_win_rate: 0.5
- v16_lose_rate: 0.5
- tie_rate: 0.0
- parse_err: 0
- provisional: False

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.874 | 0.8717 |
| distinct char-4 (mean) | 0.9929 | 0.9728 |
| overlap consec char-2 | 0.0955 | 0.0814 |
| tier_hit_rate | 0.7143 | 0.6977 |
| narrations | 42 | 43 |

## Pairwise samples (first 5)

- pair#0: winner=x swap=False reason=情节推进紧凑，角色互动更生动
- pair#1: winner=y swap=True reason=情节推进更强，悬念设置好
- pair#2: winner=y swap=False reason=情节推进更具体，细节丰富，结尾有力。
- pair#3: winner=y swap=True reason=A段描写细腻，氛围营造强，情节推进自然。
- pair#4: winner=y swap=False reason=情节推进紧凑，悬念更强
