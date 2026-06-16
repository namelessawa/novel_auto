# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-iter103-seed3-50tick.json` (44 narrations)
- source v16: `docs/iter/bench-iter127-seed3-cast120.json` (40 narrations)
- paired: 40 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `v15_hold`
- reason: v16 win-rate 30.00% < 35% — v15 维持 best stable
- v16_win_rate: 0.3
- v16_lose_rate: 0.6
- tie_rate: 0.1
- parse_err: 0
- provisional: False

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.868 | 0.8707 |
| distinct char-4 (mean) | 0.9903 | 0.9922 |
| overlap consec char-2 | 0.1 | 0.0884 |
| tier_hit_rate | 0.7955 | 0.7 |
| narrations | 44 | 40 |

## Pairwise samples (first 5)

- pair#0: winner=x swap=False reason=段A情节连贯，角色内心刻画深入，推进有力。
- pair#1: winner=y swap=True reason=情节推进更直接，冲突引入迅速。
- pair#2: winner=y swap=True reason=角色互动丰富，情节冲突与悬念推进更强
- pair#3: winner=x swap=True reason=情节推进更直接，动作连贯，角色声音一致。
- pair#4: winner=x swap=False reason=段A氛围细腻，感官描写生动，情节推进连贯。
