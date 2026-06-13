# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-iter121-seed3-cast221.json` (45 narrations)
- source v16: `docs/iter/bench-iter148-seed3-cast221-sideline-r2.json` (42 narrations)
- paired: 42 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `v16_promote`
- reason: v16 win-rate 77.78% ≥ 45% — meets §4 promote bar
- v16_win_rate: 0.7778
- v16_lose_rate: 0.2222
- tie_rate: 0.0
- parse_err: 1
- provisional: False

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.8787 | 0.8741 |
| distinct char-4 (mean) | 0.9932 | 0.9917 |
| overlap consec char-2 | 0.0911 | 0.0886 |
| tier_hit_rate | 0.7333 | 0.7619 |
| narrations | 45 | 42 |

## Pairwise samples (first 5)

- pair#0: winner=y swap=True reason=段A角色内心描写更深入，情节悬念强。
- pair#1: winner=parse_error swap=False reason=json_parse_failed
- pair#2: winner=y swap=False reason=科幻元素独特，情节推进有张力
- pair#3: winner=y swap=True reason=段A角色声音细腻，情节紧张连贯。
- pair#4: winner=y swap=True reason=段A连贯性佳，角色声音鲜明，情节推进有力。
