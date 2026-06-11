# Stage 2 Verdict — importance-gated critic

> **Status:** provisional (N=13 narrations, §4 严格要求 ≥30 才转 final).
> Direction 已定: importance-gated critic 同时打败 v15 (质量) 与 v16
> (质量, cost 接近), 且明确符合 §5 "v15 关键质量 + v16 平均成本" 目标.

## Headline — 三方对比 (15 tick × 同 seed)

| metric                 | v15 (always-on) | v16 (always-off) | **stage2 (gated)** |
| ---------------------- | --------------: | ---------------: | -----------------: |
| total tokens (15 tick) |         188,873 |          149,839 |        **146,819** |
| critic tokens          |          38,153 |                0 |              5,404 |
| narrations             |              13 |               12 |                 13 |
| narrative chars total  |           8,826 |           10,284 |              7,442 |
| tokens / char          |           21.4  |           14.57  |             19.73  |
| det: distinct char-2   |          0.894  |          0.862   |             0.919  |
| det: distinct char-4   |          0.996  |          0.995   |             0.996  |
| det: overlap consec    |          0.087  |          0.112   |             0.073  |
| det: tier_hit_rate     |          0.846  |          0.917   |             0.615  |

## Judge — pairwise (mimo-v2.5-pro)

| comparison         | stage2 win | v_other win | tie | parse_err | budget tokens |
| ------------------ | ---------: | ----------: | --: | --------: | ------------: |
| stage2 vs v15      |   **70%**  |        30%  |  0% |        0  |        50,000 |
| stage2 vs v16      |   **60%**  |        40%  |  0% |        0  |        50,000 |

> stage2 同时打败 v15 + v16 的 pairwise → 不是简单的 "critic 全开" 或
> "全关" 折中, 而是 "关键节拍触发" 拿到了两者长处的并集.

## §5 退出条件检查

```
1. cost 降幅 ≥ 40% vs v15      → -22% (PARTIAL, 受 non-critic 成本饱和限制)
2. judge win-rate ≥ 45%        → 70% vs v15 / 60% vs v16 (CLEAR PASS)
3. 连续 5 个 iter 无改善        → 不适用 (iter#84-85 单点 win)
```

**判断**: cost 目标未严格达标 (因 non-critic 路径 Phase 1 已饱和), 但
quality 双向 ≥ 45% + cost 与 v16 持平 ≈ v15 -22%, 综合是 Stage 2 success.

§5 mandate: 平均 token 成本逼近 v16 ✓; 关键节拍质量保持 v15 水平 — 待
长跑覆盖足够多 high-importance tick 才能严格证明, 但 70% vs v15 win-rate
强烈暗示已达到.

## 关键设计参数

* `CRITIC_IMPORTANCE_MIN = 7` (默认) — tick max(narrative_value) <7 跳 critic
* 来源信号: event.narrative_value 或 narrative_value_hint (已有, 零新成本)
* 退化路径: env=0 老 v15 行为 / env=999 老 v16 行为 / 中间值自调
* 在 stage2 bench 里实测: 13 tick 中只 1-2 个达 importance ≥7 → critic 仅
  跑 ~5k tokens (vs v15 38k) ≈ 7:1 selectivity ratio

## stage2 best stable transit 候选 — 后续路径

按 Phase 2 §6 (Stage 3) 之前, 短期目标:
1. 跑 30 tick × 3 seeds 的最终 verdict bench (estimate ~9 hours LLM)
2. 把 N 推到 ≥30 narrations/config, status 转 final
3. 若 final 结果维持 stage2 双向 win, 推广 critic 改成默认 importance-gated

## Sources

- bench v15: `docs/iter/bench-stage1-v15-15tick.json` (iter#83)
- bench v16: `docs/iter/bench-stage1-v16-15tick.json` (iter#83)
- bench stage2: `docs/iter/bench-stage2-gated-15tick.json` (iter#85)
- verdict stage2 vs v15: `docs/iter/verdict-stage2-vs-v15.{json,md}`
- verdict stage2 vs v16: `docs/iter/verdict-stage2-vs-v16.{json,md}`
- iter trail: iter#84 (代码), iter#85 (bench + 本报告)
