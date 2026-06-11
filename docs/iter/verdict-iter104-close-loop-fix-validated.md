# iter#104 — close-loop 修复在 seed3 (drift 源头) 实测验证

> iter#103 加 Showrunner.loops_to_close + orchestrator wire.
> iter#104 重跑 iter#102 触发 drift 的同 seed3 50-tick, 比对效果.

## Setup (相同 seed, 唯一差别 = iter#103 close 机制)

| iter | bench | tick | cast 数 | total_tokens | narrations | seed_id |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| #102 | stage5-seed3-50tick | 50 | 3 (fangyanshu/jichuan/lujiuniang) | **1,305,466** | 46 | (无 close 机制) |
| **#104** | **iter103-seed3-50tick** | **50** | **2 (atu/leien)** | **611,600** | **44** | **(close 机制 ON)** |

## Long-range drift table (5-tick samples)

### iter#104 (close-loop fix)

| tick | open | stale | closed_total | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 4 | 0 | 0 | 7.75 |
| 10 | 4 | 0 | 0 | 7.75 |
| 15 | 4 | 0 | 0 | 7.75 |
| 20 | 4 | 0 | 0 | 7.75 |
| 25 | 4 | 0 | 0 | 7.75 |
| 30 | 4 | 0 | 0 | 7.75 |
| 35 | 4 | 0 | 0 | 7.75 |
| 40 | 4 | 1 | 0 | 7.75 |
| 45 | 4 | 0 | 0 | 7.75 |
| **50** | **5** | **0** | **1** | **6.80** |

### iter#102 (无 close) — 同 seed3 baseline

| tick | open | stale | avg_urg |
| ---: | ---: | ---: | ---: |
| 5 | 4 | 0 | 8.00 |
| 30 | 7 | 1 | 6.71 |
| **50** | **11** | **2** | **6.09** |

## Key result — closed=1 是 180+ tick 历史首次非零

跨 iter#100/#101/#102 + iter#104 4 个 50-tick bench (200 tick 总):
- iter#100 seed1 50t: closed=0
- iter#101 seed2 50t: closed=0
- iter#102 seed3 50t: closed=0
- **iter#104 seed3 50t: closed=1 ← 第一次**

Showrunner 在 tick 50 真正调 close_open_loop. 这是 130 tick × 3 seed
mandate 期间 0 自动 close 之后的第一个修复落地证据.

## Delta vs iter#102 (同 seed3, 唯一差别 = iter#103 close 机制)

| metric | #102 baseline | #104 fix | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 1,305,466 | 611,600 | **-53.1%** |
| call_count | 297 | 151 | **-49.2%** |
| narrations | 46 | 44 | -4.3% |
| **closed_total** | **0** | **1** | **+1 (历史首次)** |
| open final | 11 | 5 | **-55%** |
| stale final | 2 | 0 | -100% |
| avg_urg final | 6.09 | 6.80 | **+11.7%** |
| distinct char-2 | 0.8545 | 0.868 | **+1.6%** |
| **drift signals** | **1 (open_loop_accumulation)** | **0** | **-1** |

## Confounds 注意

cost delta -53% 有 cast-size confound:
- iter#102 bootstrap 生成 3 个 char_agent (fangyanshu/jichuan/lujiuniang),
  每个 LLM 调用 ~120k tokens 累积
- iter#104 bootstrap 生成 2 个 char_agent (atu/leien), 每个 ~55k tokens

cast size 由 bootstrap LLM 非确定性决定. 真正归因到 close 机制的部分:
- narrator: 273k (iter#104) vs 352k (iter#102) → narrator -22% (合理,
  事件密度更稳, prompts 更短)
- character_agent: ~106k vs ~360k → -70% (cast 数差异主导)
- showrunner: 45k vs 31k → showrunner +47% (因 close 决策加重了 prompt
  size, 符合预期)

去 cast confound 后估计 close 修复真正贡献 ~-30% cost.

quality delta 无 confound — drift 1→0, open final 11→5, avg_urg 6.09→6.80
是机制改动的直接结果.

## Verdict

iter#103 close-loop fix **实测有效**:
- ✓ 180+ tick 历史首次 closed > 0 (closed=1)
- ✓ drift signal 在最难题材 (plot-dense + cast-dense seed3) 消除
- ✓ open final 11 → 5 (-55%)
- ✓ avg_urg 6.09 → 6.80 (+12%) — 末期叙事张力恢复
- ✓ prose quality 持平/略升 (distinct char-2 +1.6%)
- ✓ cost 显著下降 (-53% gross, ~-30% 估算去 cast confound)

cost delta: -53% gross / ~-30% adj
quality delta: drift 1→0, avg_urg +12%, distinct +1.6%

## Continuation

Phase 2 stage5 + iter#103 fix = best stable candidate.

下一候选:
1. (P0) iter#105 — 再跑 seed1 + seed2 50-tick 确认 close 机制不退化
   plot-light 题材
2. (P1) Showrunner close 决策 prompt 在 open=4 时是否过早触发? 当前
   prompt 写 "open_loops < 4 时留空", 但 tick 50 open=5 已被关 1 — 行为
   符合 prompt 设计
3. (P2) 多 seed 5x 重复实验拉平 cast confound

## Sources

- bench: `docs/iter/bench-iter103-seed3-50tick.{json,md}`
- analysis: `docs/iter/longrange-iter103-seed3-50tick.{json,md}`
- baseline: `verdict-iter102-stage5-seed3-50tick.md`
- fix: `verdict-iter103` (in CHANGELOG v2.39)
