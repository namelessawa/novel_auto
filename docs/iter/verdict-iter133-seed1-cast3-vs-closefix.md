# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-iter103-seed1-50tick.json` (44 narrations)
- source v16: `docs/iter/bench-iter126-seed1-cast120.json` (42 narrations)
- paired: 42 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `v15_hold`
- reason: v16 win-rate 20.00% < 35% — v15 维持 best stable
- v16_win_rate: 0.2
- v16_lose_rate: 0.8
- tie_rate: 0.0
- parse_err: 0
- provisional: False

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.8689 | 0.8913 |
| distinct char-4 (mean) | 0.9916 | 0.9944 |
| overlap consec char-2 | 0.0843 | 0.0908 |
| tier_hit_rate | 0.75 | 0.7381 |
| narrations | 44 | 42 |

## Pairwise samples (first 5)

- pair#0: winner=x swap=True reason=情节推进紧凑，角色声音更主动。
- pair#1: winner=y swap=True reason=角色声音突出，情节推进连贯
- pair#2: winner=x swap=False reason=A段情节推进更流畅，角色互动增强连贯性。
- pair#3: winner=x swap=True reason=对话推进情节高效，角色互动鲜明。
- pair#4: winner=x swap=True reason=情节推进更快，角色对话更生动
