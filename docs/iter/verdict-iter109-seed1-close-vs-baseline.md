# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-stage5-seed1-50tick-r.json` (41 narrations)
- source v16: `docs/iter/bench-iter103-seed1-50tick.json` (44 narrations)
- paired: 41 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `v16_promote`
- reason: v16 win-rate 70.00% ≥ 45% — meets §4 promote bar
- v16_win_rate: 0.7
- v16_lose_rate: 0.3
- tie_rate: 0.0
- parse_err: 0
- provisional: False

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.8825 | 0.8689 |
| distinct char-4 (mean) | 0.9937 | 0.9916 |
| overlap consec char-2 | 0.0967 | 0.0843 |
| tier_hit_rate | 0.878 | 0.75 |
| narrations | 41 | 44 |

## Pairwise samples (first 5)

- pair#0: winner=y swap=False reason=B 在情节推进和角色声音上更突出。
- pair#1: winner=x swap=True reason=情节推进更丰富，悬念设置突出。
- pair#2: winner=y swap=False reason=段B引入角色互动，情节推进更有效。
- pair#3: winner=x swap=False reason=情节紧凑，环境描写生动，推进迅速。
- pair#4: winner=y swap=False reason=段B情节推进好，角色声音强。
