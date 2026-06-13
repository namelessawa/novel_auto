# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-iter122-seed1-cast221.json` (42 narrations)
- source v16: `docs/iter/bench-iter144-seed1-cast221-sideline.json` (46 narrations)
- paired: 42 (truncated to min)
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
| distinct char-2 (mean) | 0.8649 | 0.8563 |
| distinct char-4 (mean) | 0.9922 | 0.9898 |
| overlap consec char-2 | 0.0861 | 0.1 |
| tier_hit_rate | 0.5714 | 0.8043 |
| narrations | 42 | 46 |

## Pairwise samples (first 5)

- pair#0: winner=y swap=False reason=情节推进更紧凑，悬念设置更好
- pair#1: winner=y swap=True reason=环境描写细腻，悬念设置巧妙。
- pair#2: winner=y swap=True reason=描写细腻，氛围营造强，情节悬念突出
- pair#3: winner=x swap=False reason=情节推进连贯，角色声音鲜明。
- pair#4: winner=y swap=True reason=A段心理描写细腻，情节推进更清晰。
