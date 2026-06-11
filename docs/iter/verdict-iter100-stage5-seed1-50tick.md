# iter#100 — stage5 cross-stage seed1 50 tick (Phase 2 milestone)

> verdict-phase2-final.md "Continuation" §1 candidate: stage5 50 tick × 3 seed
> 第一个 50-tick run. 验证 iter#96 open_pressure 在长程是否仍 hold.

## Setup

| run | seed | ticks | config |
| --- | --- | ---: | --- |
| stage4-seed1 (iter#94) | 蒸汽朋克档案馆 | 50 | stage4 (无 open_pressure) |
| **stage5-seed1 (iter#100)** | **同上** | **50** | **stage5 (+iter#96 open_pressure)** |
| stage5-seed2 (iter#95-96) | 民国上海 | 30 | stage5 |
| stage5-seed3 (iter#97) | 末世废土 | 30 | stage5 |

## Long-range drift table (per 5-tick sample)

### stage5 seed1 50 tick (iter#100)

| tick | open | stale | closed | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 4 | 0 | 0 | 6.5 |
| 10 | 4 | 0 | 0 | 6.5 |
| 15 | 4 | 0 | 0 | 6.5 |
| 20 | 4 | 0 | 0 | 6.5 |
| 25 | 4 | 0 | 0 | 6.5 |
| 30 | 4 | 0 | 0 | 6.5 |
| **35** | **6** | **0** | **0** | **6.0** |
| **40** | **6** | **0** | **0** | **6.0** |
| **45** | **6** | **1** | **0** | **6.0** |
| **50** | **6** | **1** | **0** | **6.0** |

### stage4 seed1 50 tick (iter#94 baseline)

| tick | open | stale | avg_urg |
| ---: | ---: | ---: | ---: |
| 5  | 4 | 0 | 7.25 |
| 30 | 5 | 2 | 6.80 |
| 50 | 5 | 1 | 6.80 |

## 解读

**stage5 50 tick verdict: 0 drift signals**

* open_count 在 tick 30→35 从 4 升到 6 (open_pressure 触发的 cap)
* tick 35-50 期间 **持续 hold 在 6, 未破 cap** — 软上限工作 ✓
* stale 整个 50 tick 仅 1 个 (tick 45 短暂出现) — vs stage4 时持续 1-2 个
* 0 drift signals (stage4 也是 0, 但这是 plot-density 题材首次 50-tick 验证)

## Cost / quality delta vs stage4

| metric | stage4-seed1-50t | stage5-seed1-50t | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 540,474 | **521,767** | **-3.5%** |
| call_count | n/a | 123 | n/a |
| narrations | 40 | **41** | +2.5% |
| distinct char-2 | 0.895 | 0.8825 | -1.4% |
| open at tick 50 | 5 | 6 | +1 (within cap) |
| stale at tick 50 | 1 | 1 | 0 |
| drift signals | 0 | **0** | 同 |
| avg_urg final | 6.80 | 6.00 | -0.8 |

## Verdict

stage5 **cross-stage seed1 50-tick robust 已验证**:
* tokens -3.5% (cost 略降)
* drift 0 (与 stage4 持平, 0/0)
* prose quality 持平 (distinct char-2 仅 -1.4%, 仍在 0.88-0.91 三 seed 区间)
* open_pressure 软上限在 plot-density 题材 50 tick 范围内 hold

## Phase 2 §4 N≥30 narrations × 3 seed mandate

| seed | narrations | 状态 |
| --- | ---: | --- |
| seed1 (蒸汽朋克 50 tick) | **41** | ✓ |
| seed2 (民国 30 tick) | 22 | 还差 8 narrations |
| seed3 (末世 30 tick) | 21 | 还差 9 narrations |

**seed1 单独达成 N≥30**. 完整 mandate (3 seed 全 N≥30) 需要 seed2/3 加跑.

## Continuation

stage5 stable. 下一候选:
1. seed2/3 加跑到 50 tick → 完成 §4 mandate
2. 进一步压 cost — narrator 50.5% token share, prompt cache 探索
3. seed1 distinct char-2 -1.4% — Phase 2 §3 prose dimension 持续观测
4. avg_urg 末期 6.0 vs 6.8 — 是否健康 trend (loop 关闭让全局 urg 降, 或是 LLM 主观 fatigue) 需要 quality judge bench

## Sources

- bench: `docs/iter/bench-stage5-seed1-50tick-r.{json,md}`
- analysis: `docs/iter/longrange-stage5-seed1-50tick.{json,md}`
- baseline: `verdict-stage4.md`, `verdict-phase2-final.md`
