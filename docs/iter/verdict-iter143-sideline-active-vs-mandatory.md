# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-iter140-seed1-sideline-active.json` (41 narrations)
- source v16: `docs/iter/bench-iter142-seed1-sideline-mandatory-r.json` (41 narrations)
- paired: 41 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `v16_promote`
- reason: v16 win-rate 66.67% ≥ 45% — meets §4 promote bar
- v16_win_rate: 0.6667
- v16_lose_rate: 0.3333
- tie_rate: 0.0
- parse_err: 1
- provisional: False

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.8643 | 0.8739 |
| distinct char-4 (mean) | 0.9904 | 0.992 |
| overlap consec char-2 | 0.0983 | 0.0921 |
| tier_hit_rate | 0.7317 | 0.6829 |
| narrations | 41 | 41 |

## Pairwise samples (first 5)

- pair#0: winner=y swap=True reason=段A连贯生动，角色鲜明，情节推进强。
- pair#1: winner=y swap=False reason=情节推进深入，悬念设置强
- pair#2: winner=x swap=False reason=连贯紧凑，紧张感强，角色行动果断
- pair#3: winner=x swap=False reason=情节紧张推进快，角色声音鲜明
- pair#4: winner=y swap=True reason=情节紧凑，悬念递进，角色动作连贯。
