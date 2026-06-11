# iter#95 — Stage 4 cross-genre validation

> stage4 三件套 (iter#90-92) 在第二个题材 seed 上的稳健性测试.

## Setup

| run | seed | ticks | total_tokens | narrations |
| --- | ---- | ----: | -----------: | ---------: |
| stage4-seed1 (iter#94) | 蒸汽朋克档案馆 (50 tick) | 50 | 540,474 | 40 |
| stage3-seed1 (iter#89) | 同上 (50 tick, no stage4 fixes) | 50 | 509,417 | 42 |
| **stage4-seed2 (iter#95)** | **民国上海密码员** | **30** | **307,630** | **28** |

## Cross-genre drift table (per 5-tick sample)

### seed2 (民国上海, 30 tick, stage4)

| tick | open | stale | avg_urg |
| ---: | ---: | ----: | ------: |
|   5  |   4  |   0   |   7.25  |
|  10  |   4  |   0   |   7.25  |
|  15  |   4  |   0   |   7.25  |
|  20  |   4  |   0   |   7.25  |
|  25  |   6  |   0   |   6.50  |
|  30  |   7  |   2   |   6.29  |

### seed1 (蒸汽朋克, 50 tick, stage4 — 截到 tick 30 对比)

| tick | open | stale | avg_urg |
| ---: | ---: | ----: | ------: |
|   5  |   4  |   0   |   7.25  |
|  10  |   4  |   0   |   7.25  |
|  15  |   5  |   0   |   6.80  |
|  20  |   5  |   0   |   6.80  |
|  25  |   5  |   2   |   6.80  |
|  30  |   5  |   2   |   6.80  |

## 解读

**prose-level 跨题材稳健 ✓**:
* distinct char-2: 0.895 / 0.895 (持平, 与 seed1 完全一致)
* overlap consec char-2: 0.059 (seed2) vs 0.076 (seed1) — seed2 **更佳**
* tier_hit_rate 等等也持稳

**plot-level drift 部分缓解, 但跨题材仍有触发**:
* stage4 seed2 30 tick open 4→7 (+75%)
* stage4 seed1 50 tick open 4→5 (+25%)
* stage3 seed1 50 tick open 5→9 (+80%) ← 基线
* seed2 累积率 (在 30 tick 内) 高于 seed1, 仍触发 `open_loop_accumulation`
  drift signal (虽然只 1 个, vs stage3 时 2 个)
* avg_urgency 同步从 7.25 跌到 6.29 — 民国题材确实 (LLM 主观) 生成
  更多 open thread

**两种解读 (待数据进一步评估):**
1. 题材天然差异 — 民国密码 / 谍战 / 抑郁 这种 setup 客观上需要更多
   plot thread, 不该被强行压制
2. Stage 4 阈值需要题材自适应 — 当前 stale≥3 才触发偏好关旧,
   对 plot 密集题材应当下调 (例如 stale≥2)

## §6 cross-genre exit assessment

Stage 3 §6 exit "≥1 新优化面登记" 已在 iter#89 达成. iter#95 增加新信息:

**新登记 (iter#96+ 候选)**: stale 阈值可能需要按 open_loop "natural growth
rate" 自适应. 简单实现: 当 open_loop_count 单 5-tick 窗口涨 ≥ 2 时,
临时把 stale 触发阈值从 3 降到 2 — 防 plot 密集题材冲破 cap.

## Sample (seed 2)

> 阁楼的灯泡是新换的, 钨丝亮得发青. 周衡把电报放在桌上, 纸边压住一只
> 黄铜烟灰缸 — 烟灰缸里只有一根没抽完的烟, 已经熄了几小时...

文字 quality 与 seed1 同水准 — Phase 2 §3 prose dimension 跨题材 robust.

## Sources

- bench seed2: `docs/iter/bench-stage4-seed2-30tick.{json,md}`
- analysis seed2: `docs/iter/longrange-stage4-seed2-30tick.{json,md}`
- baseline seed1 stage4: `verdict-stage4.md` (iter#94)

## Verdict

stage4 cross-genre **partially validated**:
* prose-level 完全 robust (跨题材测试通过)
* plot-level drift cap **部分** 跨题材 — 减缓但不消除
* 新优化面 iter#96+ 登记: stale 阈值题材自适应

stage4 暂时维持 best stable candidate. 多 seed × ≥30 tick 是后续严格化
方向 (Phase 2 §4 N≥30 narrations × 3 seed mandate 还差 1 seed).
