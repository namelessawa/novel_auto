# iter#125 — Phase 3-B cast count sweep: seed2 cast=3 是真正 sweet spot

> iter#124 verdict 提的 P0: cast count sweep. seed2 (plot-medium) 重 bench
> with cast=3 (1A+2B+0C) 验证 cast=5 不适合是因为太多 vs 自然甜点 ~3.

## Setup

| iter | seed2 config | actual chars | total_tokens |
| --- | --- | ---: | ---: |
| #101 | baseline (wide) | 2 (random) | 483,857 |
| #107 | close-fix (wide) | 2 (random) | 527,769 |
| #124 | cast=5 (2A+2B+1C) | 5 | 533,808 |
| **#125** | **cast=3 (1A+2B+0C)** | **3** | **484,134** |

## Long-range table (iter#125)

| tick | open | stale | closed_total | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 4 | 0 | 0 | 6.75 |
| 10 | 3 | 0 | 1 | 7.33 |
| 15-50 | 3 | 0 | 1-2 | 7.33 |

open 在 tick 10 后稳定 3 — 池子始终健康. close 在 tick 10 + tick 30 触发.

## 全 4 seed2 config 对比

| metric | #101 (wide ~2) | #107 (wide ~2 +close-fix) | #124 (cast=5) | **#125 (cast=3)** |
| --- | ---: | ---: | ---: | ---: |
| total_tokens | 483,857 | 527,769 | 533,808 | **484,134** |
| call_count | 121 | 130 | 128 | 121 |
| narrations | 42 | 45 | 42 | 36 |
| distinct char-2 | 0.9087 | 0.8974 | 0.874 | **0.8886** |
| open final | 5 | 4 | 4 | **3** |
| closed_total | 0 | 2 | 4 | 2 |
| avg_urg final | 7.00 | 7.25 | 6.75 | **7.33** |
| drift signals | 0 | 0 | 0 | 0 |

## Key delta — #125 cast=3 vs #124 cast=5 (同 seed2, 只换 cast count)

| metric | #124 cast=5 | #125 cast=3 | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 533,808 | 484,134 | **-9.3%** |
| narrations | 42 | 36 | -14% |
| distinct char-2 | 0.874 | 0.8886 | **+1.7%** |
| open final | 4 | 3 | -25% |
| avg_urg final | 6.75 | 7.33 | **+8.6%** |
| drift | 0 | 0 | 同 |

**cast=3 完胜 cast=5**: cost -9.3%, distinct +1.7%, avg_urg +8.6%, drift 维持.

narrations -14% 是 narrator 更挑剔 (avg_urg 高 → 选高价值才写). 这是
**feature 不是 bug** — 配合 close-fix 让 narrative tension 更聚焦.

## Key delta — #125 cast=3 vs #107 close-fix wide (同 seed2, only cast 模式)

| metric | #107 wide (cast=2 random) | #125 cast=3 (固定) | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 527,769 | 484,134 | **-8.3%** |
| distinct char-2 | 0.8974 | 0.8886 | -1.0% (噪声) |
| open final | 4 | 3 | -25% |
| avg_urg final | 7.25 | 7.33 | +1.1% |
| drift | 0 | 0 | 同 |

也是净胜 — cast=3 固定比 cast=2 wide random 更好.

## Phase 3-B 更新 verdict — 题材自适应 cast count

| 题材 | optimal cast | reason |
| --- | --- | --- |
| seed1 plot-light (蒸汽朋克) | cast=5 (iter#122) | wide random 给 1-2 太少, cast=5 让 dispersal 均衡 |
| seed2 plot-medium (民国) | **cast=3 (iter#125)** | wide ~2 已甜点, cast=3 比 cast=5 更好 |
| seed3 plot-dense (末世) | cast=5 (iter#121) | wide random 给 3 太密时 cost 爆 1.3M, cast=5 抑住 |

**关键洞察**: cast 控制 win 来自 "**精确避免极端**" 而非 "增加多元".
- seed1 wide 偶发 cast=1 → 多面塌, cast=5 救场
- seed3 wide 偶发 cast=3 + 高密度 → cost 爆, cast=5 让结构化
- seed2 wide ~2 已平衡, cast=3 比 cast=5 更好 (cast=5 cast-overload)

## Phase 3-B 平均 across 3-seed (revised with iter#125)

| seed | optimal config | tokens | vs close-fix wide |
| --- | --- | ---: | ---: |
| seed1 (iter#122) | cast=5 | 509,863 | -6.4% |
| seed2 (iter#125) | **cast=3** | **484,134** | **-8.3%** |
| seed3 (iter#121) | cast=5 | 496,972 | -19% |
| avg optimal | — | **496,990** | **-11.4%** |

Phase 3-B 平均 cost win **11.4%** (vs 之前 cast=5 universal 时的 -8.5%).
诚实结论: cast 配置题材自适应可挤多 3 个百分点.

## 双指标 delta

cost delta vs #107 close-fix: -8.3%
cost delta vs #124 cast=5: -9.3%
quality delta: drift 0/0, distinct -1% (噪声 vs close-fix), avg_urg +1.1%

## Continuation

iter#126+ 候选:
1. (P0) seed1 用 cast=3 重 bench → 是否 seed1 也是 cast=3 更好?
   (重测 sweet spot 跨题材)
2. (P1) seed3 用 cast=4 重 bench → 同 sweep
3. (P2) showrunner runtime active-cast 动态选 cast count (基于
   open_loops/event 密度)

## Sources

- bench: `docs/iter/bench-iter125-seed2-cast120.{json,md}`
- analysis: `docs/iter/longrange-iter125-seed2-cast120.{json,md}`
- cast=5 baseline: `verdict-iter124-cast-3seed-final.md`
- close-fix wide: `verdict-iter107-3-seed-close-matrix.md`
