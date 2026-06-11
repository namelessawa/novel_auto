# iter#102 — stage5 seed3 50 tick (mandate complete + drift surfaced)

> Phase 2 §4 N≥30 × 3-seed mandate 第三个 50-tick leg.
> seed3 (末世废土移动城市) 是 cast-dense + plot-dense 复合密度题材.

## Mandate completion table

| seed | 题材 | narrations | drift signals | iter |
| --- | --- | ---: | ---: | --- |
| seed1 | 蒸汽朋克档案馆 | 41 | 0 | #100 |
| seed2 | 民国上海密码员 | 42 | 0 | #101 |
| **seed3** | **末世废土移动城市** | **46** | **1 (open_loop_accumulation)** | **#102** |

**§4 N≥30 × 3-seed mandate: 完成 (3/3 seed 全 N≥30)** ✓

## Long-range drift table (5-tick samples)

### stage5 seed3 50 tick (iter#102)

| tick | open | stale | closed | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 4 | 0 | 0 | 8.0 |
| 10 | 5 | 0 | 0 | 7.4 |
| 15 | 6 | 0 | 0 | 7.0 |
| 20 | 6 | 0 | 0 | 7.0 |
| 25 | 6 | 0 | 0 | 7.0 |
| 30 | 7 | 1 | 0 | 6.71 |
| 35 | 9 | 1 | 0 | 6.33 |
| 40 | 10 | 1 | 0 | 6.2 |
| 45 | 10 | 1 | 0 | 6.2 |
| **50** | **11** | **2** | **0** | **6.09** |

**drift**: open 累积 4→11 (+175%), avg_urg 衰减 8.0→6.09 (-24%), 跨 35-50 tick 失控.

## Cost / quality delta vs iter#100/#101

| metric | seed1 50t | seed2 50t | **seed3 50t** | seed3 vs avg |
| --- | ---: | ---: | ---: | --- |
| total_tokens | 521,767 | 483,857 | **1,305,466** | **+159% (2.6x)** |
| call_count | 123 | 121 | **297** | +143% |
| narrations | 41 | 42 | 46 | +12% |
| distinct char-2 | 0.8825 | 0.9087 | 0.8545 | -4.4% |
| open final | 6 | 5 | **11** | +120% |
| stale final | 1 | 0 | 2 | +200% |
| **closed final** | **0** | **0** | **0** | **0 跨 3 seed 全部** |
| avg_urg final | 6.00 | 7.00 | 6.09 | -6.4% |
| drift signals | 0 | 0 | **1** | new |

## Key findings

### Finding 1: open_pressure soft cap 在 cast-dense + plot-dense 复合题材失效

末世废土 setup 在 LLM 主观看来需要更多 plot thread, soft signal "high pressure"
没法压制. tick 25→50 期间 open 从 cap=6 升到 11.

### Finding 2: closed=0 跨 3 seed 全部 ← 更深问题

整个 stage5 实验 (130 个 tick 累计) **零次 loop 被关闭** (非 stale 回收).
说明:
- 当前 close 机制可能依赖 Narrator 主动 resolve, 但 Narrator 没有显式 "你
  必须关 X loop" 指令
- 或 Showrunner 推荐没有触达 loop 关闭操作
- stale-reaping 只能延后, 不能真正释放叙事张力

**iter#103 候选: 显式 close-loop 机制** — Narrator/Showrunner 在 open ≥ cap
时被 prompt 强制选 1 个 loop resolve, 而不是只依赖 EventInjector 不再 open.

### Finding 3: cast-dense 题材 cost 跳 2.6x

seed3 297 calls vs seed1/2 ~120 calls. 顶层 by_agent:
- narrator=352k
- world_simulator=157k
- char_fangyanshu=125k, char_jichuan=119k, char_lujiuniang=117k

cast 多 → character_agent 每 tick 都跑 → cost 累积. character_agent 的
batch_decide 已是 concurrency 优化, 单 tick latency OK, 但 token spend
线性 with cast count.

**iter#103+ 候选: showrunner cap 主动 cast (max active cast = 3-4)** 防 plot 过
散.

### Finding 4: distinct char-2 跨 3 seed 区间扩到 [0.855, 0.909]

seed3 最低 0.8545 (vs seed1 0.883, seed2 0.909). Phase 2 §3 prose dim 在
高密度题材有 slight 退化, 仍 > 0.85 threshold, 可接受但需要 monitor.

## Verdict

Phase 2 §4 N≥30 × 3-seed mandate **完成** ✓.

stage5 verdict **跨题材 conditional robust**:
- plot-light / plot-medium seed (seed1 蒸汽朋克 / seed2 民国): 0 drift, 配置稳定
- plot-heavy + cast-heavy seed (seed3 末世废土): drift 触发, soft cap 失效

iter#103 候选明确化:
1. (P0) 显式 close-loop 机制 — closed=0 是真正的 leakage
2. (P1) seed3 cost 2.6x — showrunner active-cast cap
3. (P2) char-2 distinct 高密度题材轻微退化 — 观测

## Sources

- bench: `docs/iter/bench-stage5-seed3-50tick.{json,md}`
- analysis: `docs/iter/longrange-stage5-seed3-50tick.{json,md}`
- prior: `verdict-iter100-stage5-seed1-50tick.md`, `verdict-iter101-stage5-seed2-50tick.md`
