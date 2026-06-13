# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-iter146-seed2-cast221-sideline.json` (43 narrations)
- source v16: `docs/iter/bench-iter155-seed2-cast221-budget1200-r.json` (40 narrations)
- paired: 40 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `stage2_open`
- reason: v16 win-rate 40.00% ∈ [35%, 45%) — critic 不应是 binary 开关, Stage 2 自适应分配立项
- v16_win_rate: 0.4
- v16_lose_rate: 0.6
- tie_rate: 0.0
- parse_err: 0
- provisional: False

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.8717 | 0.886 |
| distinct char-4 (mean) | 0.9728 | 0.9957 |
| overlap consec char-2 | 0.0814 | 0.0791 |
| tier_hit_rate | 0.6977 | 0.65 |
| narrations | 43 | 40 |

## Pairwise samples (first 5)

- pair#0: winner=x swap=True reason=段B悬念设置更佳，情节推进有力
- pair#1: winner=x swap=False reason=段A情节推进更紧凑，角色动作连贯。
- pair#2: winner=x swap=False reason=情节连贯，感官描写细腻，推进有力。
- pair#3: winner=x swap=True reason=B段细节更丰富，情节推进更紧凑悬疑。
- pair#4: winner=y swap=True reason=环境细节丰富，悬念营造自然。
