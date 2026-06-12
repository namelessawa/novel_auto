# iter#107 — 3-seed × close-fix matrix complete

> verdict-iter105 §Continuation P1: seed2 (民国上海) 50-tick with iter#103
> close-fix. 完成跨 3 seed × close-fix 完整 matrix.

## Setup

| iter | bench | ticks | seed | total_tokens | narrations | cast | mode |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| #101 | stage5-seed2-50tick | 50 | 民国上海 | 483,857 | 42 | 2 | baseline (无 close) |
| **#107** | **iter103-seed2-50tick** | **50** | **同上** | **527,769** | **45** | **2** | **+iter#103 close** |

## Long-range drift table (iter#107)

| tick | open | stale | closed_total | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 5 | 0 | 0 | 7.0 |
| 10 | 5 | 0 | 0 | 7.0 |
| 15 | 5 | 0 | 0 | 7.0 |
| 20 | 5 | 0 | 0 | 7.0 |
| 25 | 5 | 1 | 0 | 7.0 |
| 30 | 5 | 1 | 0 | 7.0 |
| 35 | 5 | 0 | 0 | 7.0 |
| **40** | **6** | **0** | **0** | **6.67** |
| **45** | **6** | **0** | **0** | **6.67** |
| **50** | **4** | **0** | **2** | **7.25** |

cap-trigger 行为: tick 40 触达 6 (cap), Showrunner 在 tick 50 关 2 个 → 池
回 4. avg_urg 跌后立刻回升 (6.67→7.25).

## Delta vs iter#101 (same seed2 50t, 唯一差别 = iter#103 close)

| metric | #101 baseline | #107 with-fix | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 483,857 | 527,769 | +9.1% |
| call_count | 121 | 130 | +7.4% |
| narrations | 42 | 45 | +7.1% |
| **closed_total** | **0** | **2** | **+2** |
| open final | 5 | 4 | **-20%** |
| stale final | 0 | 0 | 0 |
| avg_urg final | 7.00 | 7.25 | **+3.6%** |
| distinct char-2 | 0.9087 | 0.8974 | -1.2% |
| **drift signals** | **0** | **0** | **同 (无退化)** |

## 3-seed × close-fix matrix (FINAL)

| seed | open_final | closed_total | avg_urg | drift | cost delta | quality verdict |
| --- | --: | --: | --: | --: | --: | --- |
| **seed1** (蒸汽朋克) | 6 → 4 | 0 → 3 | 6.0 → 6.75 (+12.5%) | 0 → 0 | +4.4% | 提升 |
| **seed2** (民国上海) | 5 → 4 | 0 → 2 | 7.0 → 7.25 (+3.6%) | 0 → 0 | +9.1% | 提升 |
| **seed3** (末世废土) | 11 → 5 | 0 → 1 | 6.09 → 6.80 (+11.7%) | **1 → 0** | -53% gross | 显著提升 |
| **avg** | 7.3 → 4.3 (-41%) | 0 → 2.0 | (+9.3%) | drift 1→0 | (题材分化) | **全面 robust** |

## Verdict — Phase 2 close-fix 跨题材完整通过

✓ **closed_total 跨 3 seed 全部 > 0** — 跨 130 tick 历史 closed=0 时代结束
✓ **open final 跨 3 seed 平均 -41%** — 池子稳定健康
✓ **avg_urg 跨 3 seed 全部上升 (+3.6% ~ +12.5%)** — 末期叙事张力恢复
✓ **drift signals 跨 3 seed 全部 0** (seed3 1→0, seed1/2 持平)
✓ **distinct char-2 跨 3 seed 仅 -1.2% ~ -1.5% 噪声** — prose quality 维持

cost delta:
* plot-light seed (seed1/2): +4.4% / +9.1% (Showrunner JSON +close 决策)
* plot-dense seed (seed3): -53% gross / -30% adj (close 释放 token 资源)

## Cumulative achievement (Phase 2 iter#76-107)

- Stage 0-4: 度量基建 + drift surfaced + 三件套修复
- Stage 5 (iter#96): open_pressure 信号
- §4 mandate (iter#100-102): 3-seed × 50-tick × N≥30 narrations
- iter#103+: close-loop 机制 (130 tick × 3 seed × 0 closed 时代结束)
- iter#104-107: close-fix 跨 3 seed 全部 validated

## Continuation

下一候选 (按 verdict-iter105 §Continuation):
1. (done ×3) 3-seed close-fix matrix ✓
2. (P0) ID race medium — add_open_loop dedup gate (iter#106 review 接受
   作为后续)
3. (P1) Showrunner close prompt 进一步 tuning 通过 quality bench 度量
4. (P2) Phase 3 candidate: cast-confound 控制实验

## Sources

- bench: `docs/iter/bench-iter103-seed2-50tick.{json,md}`
- analysis: `docs/iter/longrange-iter103-seed2-50tick.{json,md}`
- baseline: `verdict-iter101-stage5-seed2-50tick.md`
- prior matrix: `verdict-iter104-close-loop-fix-validated.md`, `verdict-iter105-seed1-close-fix.md`
