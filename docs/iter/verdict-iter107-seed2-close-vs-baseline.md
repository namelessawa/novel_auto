# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-stage5-seed2-50tick.json` (42 narrations)
- source v16: `docs/iter/bench-iter103-seed2-50tick.json` (45 narrations)
- paired: 42 (truncated to min)
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
| distinct char-2 (mean) | 0.9087 | 0.8974 |
| distinct char-4 (mean) | 0.9959 | 0.9949 |
| overlap consec char-2 | 0.0798 | 0.0846 |
| tier_hit_rate | 0.6905 | 0.7333 |
| narrations | 42 | 45 |

## Pairwise samples (first 5)

- pair#0: winner=y swap=True reason=段A叙事连贯角色清晰情节推进强
- pair#1: winner=y swap=False reason=情节推进更强，悬疑结尾突出
- pair#2: winner=x swap=True reason=角色声音鲜明，情节推进更主动。
- pair#3: winner=x swap=False reason=描写细腻，连贯性强，角色声音突出
- pair#4: winner=y swap=True reason=情节推进有力，角色内心冲突清晰。
