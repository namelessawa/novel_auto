# iter#112 — Phase 2 close-fix FINAL verdict (3-seed × pairwise × judge)

> Phase 2 close-fix (iter#103) 完整 quality validation 闭环.
> 跨 3 seed × deterministic metrics × mimo pairwise judge 全部通过.

## 3-seed × mimo pairwise judge final matrix

| seed | source v15 (baseline) | source v16 (close-fix) | narr v15 | narr v16 | win-rate | tie | verdict |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| seed1 (蒸汽朋克档案馆) | iter#100 | iter#105 | 41 | 44 | **70%** | 0% | promote |
| seed2 (民国上海密码员) | iter#101 | iter#107 | 42 | 45 | **70%** | 0% | promote |
| seed3 (末世废土移动城市) | iter#102 | iter#104 | 46 | 44 | **80%** | 0% | promote |
| **avg / total** | — | — | **129** | **133** | **73.3%** | **0%** | **promote ×3** |

§4 promote 门槛: ≥ 45% win-rate. 3/3 seed 全部 ≥ 70%, 且最高 80% 命中
最难题材 (drift 源头), 最低 70% 在 plot-light. 一致显著.

## Deterministic + judge 全维度结果

| dimension | seed1 | seed2 | seed3 | trend |
| --- | --- | --- | --- | --- |
| closed_total v15 → v16 | 0 → 3 | 0 → 2 | 0 → 1 | **跨题材全部 > 0** |
| open final v15 → v16 | 6 → 4 | 5 → 4 | 11 → 5 | **平均 -41%** |
| avg_urg final v15 → v16 | 6.0 → 6.75 | 7.0 → 7.25 | 6.09 → 6.80 | **平均 +9.3%** |
| drift signals | 0 → 0 | 0 → 0 | **1 → 0** | seed3 drift 消除 |
| distinct char-2 | 0.8825 → 0.8689 | 0.9087 → 0.8974 | 0.8545 → 0.868 | -1.2% / -1.2% / +1.6% (noise) |
| **mimo pairwise win-rate v16** | **70%** | **70%** | **80%** | **avg 73.3%, σ ~5%** |

## §4 N≥30 mandate 完成度

| mandate | required | actual | status |
| --- | --- | --- | --- |
| narrations / seed | ≥ 30 | 41 / 42 / 46 | ✓ |
| seed count | ≥ 3 | 3 | ✓ |
| pairwise pairs / seed | ≥ 10 | 10 / 10 / 10 | ✓ |
| total judge pairs | ≥ 30 | 30 | ✓ |
| provisional? | False | False (all 3) | ✓ |

**Phase 2 mandate FULLY SATISFIED.**

## Iter trail Phase 2 (#76-112)

- Stage 0-4 (iter#76-94): 度量基建 + drift surface + 三件套修复
- Stage 5 (iter#96): open_pressure soft cap
- §4 mandate (iter#100-102): 3-seed × 50-tick × N≥30 narration
- iter#103: close-loop fix (Showrunner.loops_to_close + orchestrator wire)
- iter#104-107: close-fix 跨 3 seed deterministic 验证 (all 3 PASS)
- iter#108: add_open_loop dedup gate (review followup)
- iter#106, #110: 2 review cycles (HIGH + MEDIUM 全修)
- iter#109, #111, #112: 3-seed pairwise judge — 70/70/80% promote
- iter#112: FINAL verdict 整合 (本文档)

## Cumulative achievements

**Phase 1 (iter#3-72) Cost:**
- -77% token spend
- -83% latency
- 691 tests PASS

**Phase 2 (iter#76-112) Quality:**
- 度量基建: 60 unit tests, 跨 4 dim (det + judge × 2)
- 跨 3 seed × 50-tick × N≥30 mandate ✓
- close-loop fix: 130 tick × 3 seed × closed=0 时代结束
- mimo pairwise: 73.3% avg win-rate, σ~5%, §4 promote ×3
- 707 tests PASS
- 14 review cycles (cycle 1-14, all HIGH/MEDIUM 修)

## Continuation

Phase 2 完整 closure. 下一候选:
1. (P0) Phase 3 启动 — cast-confound 控制实验 (verdict-iter102 P1)
2. (P1) narrator prompt cache — 50.5% token share 是最大优化面
3. (P2) showrunner close prompt tuning via per-tick judge bench
4. (P3) prose diversity 度量进一步 dim

## Sources

- 3 pairwise verdicts:
  - `verdict-iter109-seed1-close-vs-baseline.{json,md}`
  - `verdict-iter107-seed2-close-vs-baseline.{json,md}`
  - `verdict-iter109-seed3-close-vs-baseline.{json,md}`
- 3 close-fix benches: `bench-iter103-seed{1,2,3}-50tick.{json,md}`
- 3 baselines: `bench-stage5-seed{1,2,3}-50tick(-r).{json,md}`
- 3 det longrange analyses: `longrange-iter103-seed{1,2,3}-50tick.{json,md}`
- Phase 2 prior verdicts: `verdict-iter{100,101,102,104,105,107}*.md`
