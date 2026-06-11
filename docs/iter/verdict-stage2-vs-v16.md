# Stage 1 Verdict — v15 vs v16

- source v15: `docs/iter/bench-stage2-gated-15tick.json` (13 narrations)
- source v16: `docs/iter/bench-stage1-v16-15tick.json` (12 narrations)
- paired: 12 (truncated to min)
- judge_calls: 10 (budget 50000)
- judge_tokens_estimated: 50000

## Verdict

- **label**: `stage2_open`
- reason: v16 win-rate 40.00% ∈ [35%, 45%) — critic 不应是 binary 开关, Stage 2 自适应分配立项
- v16_win_rate: 0.4
- v16_lose_rate: 0.5
- tie_rate: 0.1
- parse_err: 0
- provisional: True

## Det comparison

| dim | v15 | v16 |
| --- | ---: | ---: |
| distinct char-2 (mean) | 0.919 | 0.8622 |
| distinct char-4 (mean) | 0.9959 | 0.9947 |
| overlap consec char-2 | 0.0726 | 0.1121 |
| tier_hit_rate | 0.6154 | 0.9167 |
| narrations | 13 | 12 |

## Pairwise samples (first 5)

- pair#0: winner=x swap=True reason=情节推进更紧凑，角色行动有明确目标。
- pair#1: winner=x swap=True reason=情节推进更主动，悬念更紧凑
- pair#2: winner=x swap=True reason=情节推进更紧凑，角色行动果断
- pair#3: winner=y swap=True reason=段A连贯性强，角色声音清晰，情节推进明显。
- pair#4: winner=y swap=False reason=细节丰富，悬念推进，角色声音更独特。
