# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-iter103-seed2-50tick.json` (45 narrations)
- source v16: `docs/iter/bench-iter125-seed2-cast120.json` (36 narrations)
- paired: 36 (truncated to min)
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
| distinct char-2 (mean) | 0.8974 | 0.8886 |
| distinct char-4 (mean) | 0.9949 | 0.9941 |
| overlap consec char-2 | 0.0846 | 0.0818 |
| tier_hit_rate | 0.7333 | 0.7222 |
| narrations | 45 | 36 |

## Pairwise samples (first 5)

- pair#0: winner=y swap=False reason=情节推进更紧凑，角色声音鲜明。
- pair#1: winner=x swap=True reason=悬念集中，细节生动，情节推进有力
- pair#2: winner=y swap=True reason=连贯性强，情节推进快，角色互动生动。
- pair#3: winner=x swap=True reason=段B连贯性强，角色深入，情节推进明显。
- pair#4: winner=x swap=True reason=角色心理描写深入，情节推进有张力。
