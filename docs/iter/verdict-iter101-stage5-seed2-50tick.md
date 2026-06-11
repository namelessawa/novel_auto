# iter#101 — stage5 cross-genre seed2 50 tick

> Phase 2 §4 N≥30 × 3-seed mandate 第二个 50-tick leg. seed2 (民国上海)
> 是当初触发 iter#96 open_pressure 设计的 plot-dense 题材.

## Setup

| run | seed | ticks | total_tokens | narrations |
| --- | --- | ---: | ---: | ---: |
| stage4 seed2 (iter#95) | 民国上海 | 30 | 307,630 | 22 |
| stage5 seed2 (iter#95-96) | 同上 | 30 | 292,673 | 22 |
| **stage5 seed2 (iter#101)** | **同上** | **50** | **483,857** | **42** |

## Long-range drift table (5-tick samples)

### stage5 seed2 50 tick (iter#101)

| tick | open | stale | closed | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 4 | 0 | 0 | 7.5 |
| 10 | 4 | 0 | 0 | 7.5 |
| 15 | 4 | 0 | 0 | 7.5 |
| 20 | 4 | 0 | 0 | 7.5 |
| 25 | 4 | 0 | 0 | 7.5 |
| 30 | 4 | 2 | 0 | 7.5 |
| 35 | 5 | 1 | 0 | 7.0 |
| 40 | 5 | 1 | 0 | 7.0 |
| 45 | 5 | 0 | 0 | 7.0 |
| 50 | 5 | 0 | 0 | 7.0 |

### stage4 seed2 30 tick (iter#95 baseline, 无 open_pressure)

| tick | open | stale | avg_urg |
| ---: | ---: | ---: | ---: |
| 5 | 4 | 0 | 7.25 |
| 15 | 4 | 0 | 7.25 |
| 25 | 6 | 0 | 6.50 |
| **30** | **7** | **2** | **6.29** |

## 解读

**iter#96 open_pressure 在 plot-dense seed2 完整 50 tick 修复确认**:

* stage4 baseline: tick 30 已经 open=7 (突破 stage4 隐式 cap=5),
  avg_urg 6.29 (vs 起始 7.5 → -1.21 滑落).
* stage5 fix: 50 整 tick **open final=5, 始终未触及 cap=6**,
  avg_urg 末期 7.0 (vs 起始 7.5 → -0.5 轻微衰减).
* tick 30 transient stale=2 自我修复, tick 45 后 stale=0.
* 0 drift signals (vs stage4 时 1 drift signal).

## Cost / quality delta vs iter#95 stage5 seed2 30 tick

| metric | stage5 seed2 30t | stage5 seed2 50t | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 292,673 | 483,857 | +65.3% (tick +67%, 几乎线性) |
| narrations | 22 | 42 | +91% |
| tokens/narration | 13,303 | 11,520 | **-13.4%** |
| distinct char-2 | 0.913 | 0.9087 | -0.5% |
| open final | 4 (tick 30) | 5 (tick 50) | +1 (within cap) |
| stale final | 0 | 0 | 0 |
| drift signals | 0 | 0 | 0 |
| avg_urg final | 7.5 | 7.0 | -0.5 (轻微衰减) |

**tokens/narration -13.4%** 说明长程 narrator 摊销更优 (bootstrap cost
在 50 tick 上摊得比 30 tick 薄).

## Cost / quality delta vs iter#100 stage5 seed1 50 tick

| metric | seed1 50t | seed2 50t | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 521,767 | 483,857 | -7.3% (题材 variance) |
| narrations | 41 | 42 | +1 |
| distinct char-2 | 0.8825 | 0.9087 | +2.97% (seed2 prose 更鲜活) |
| open final | 6 | 5 | -1 |
| stale final | 1 | 0 | -1 |
| drift signals | 0 | 0 | 0 |
| avg_urg final | 6.0 | 7.0 | +1.0 |

seed2 全维度更好 — 这与 iter#95 时观察到的 "seed2 prose-level robust" 一致.

## Phase 2 §4 N≥30 × 3-seed mandate progress

| seed | narrations | 50-tick 状态 |
| --- | ---: | --- |
| seed1 (蒸汽朋克) | 41 | ✓ iter#100 |
| **seed2 (民国上海)** | **42** | **✓ iter#101** |
| seed3 (末世废土) | 21 (30 tick) | 还差 1 leg |

剩 seed3 50-tick 即可完成完整 mandate.

## Verdict

stage5 在 plot-dense 题材 50-tick 范围内 robust 确认 ✓.
quality 跨 2 seed × 50-tick:
- 0 drift signals
- distinct char-2 ∈ [0.883, 0.909]
- open held within cap (6) at end

cost delta vs iter#100: -7.3% (题材 variance, 非配置变化)
quality delta vs iter#100: 全部维度更优

## Sources

- bench: `docs/iter/bench-stage5-seed2-50tick.{json,md}`
- analysis: `docs/iter/longrange-stage5-seed2-50tick.{json,md}`
- prior: `verdict-iter95-multiseed.md`, `verdict-iter100-stage5-seed1-50tick.md`
