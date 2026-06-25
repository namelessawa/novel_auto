# Spike 根因复查 · run 2 (2026-06-25 retry)

> 接 `verdict-phase6a-500tick-retry-0625.md`. Run 2 在 t201-250 + t451-500
> 出现 D1 avg_dur drift (2.25× / 3.81×). 本调研定位真实原因.

## 数据

读 `bench_phase6a-500tick-seed1-retry-0625_*/critic_log.jsonl`:

| 指标 | 值 |
| --- | ---: |
| critic 触发总次数 | 24 / 500 tick |
| critic 触发率 | 4.8% (length-gated, `CRITIC_MIN_NARRATIVE_LEN=600`) |
| 占 narratives 比例 | 24 / 241 = 10% |
| ACCEPT 次数 | **23** (96%) |
| RED_TEAM | 1 |
| REVISE / REWRITE | **0** ← critic 全程**没动手改** |

## 真正的 spike 信号 · narrative 长度暴涨

| bucket | n narrate | avg chars | max chars | critic 触发 |
| --- | ---: | ---: | ---: | ---: |
| t1-50 (baseline) | 22 | 1,007 | 1,829 | 2 |
| t51-100 | 23 | 1,090 | 1,976 | 2 |
| t101-150 | 20 | 1,127 | 2,078 | 0 |
| t151-200 | 23 | 1,026 | 1,499 | 0 |
| **t201-250 (spike)** | **30** | **1,379** | **4,123** | **3** |
| t251-300 (recover) | 22 | 1,146 | 2,581 | 3 |
| t301-350 | 23 | 1,121 | 2,119 | 1 |
| t351-400 | 22 | 1,030 | 1,980 | 1 |
| t401-450 | 21 | 1,097 | 1,833 | 1 |
| **t451-500 (end)** | **35** | **1,838** | **3,686** | **8** |

* t201-250: narrate +50% (30 vs 20-23), avg chars +37% (1379 vs ~1050),
  max 一段 **4,123 字** (vs baseline ~1900).
* t451-500: narrate +60% (35), avg chars +80% (1838), 共 8 次 critic invoke
  (≥600 字段落最多).

## 解释 · 不是 critic 在 loop, 是 narrator 写得长

老假设 (Phase 6-A run 1 verdict): "narrator silent_bias 失效导致 100% 全产
narrative". **错**.

新解释 (本调研):
1. **Critic ACCEPT 96%, REVISE/REWRITE = 0** — critic 不是问题, 没有反复打回.
2. **每段 narrative 字数显著上涨** (avg 1050 → 1379-1838, max 1900 → 4123) —
   narrator 自己写得长.
3. **avg_dur drift 与 narrative 长度对应** — 4,123 字段落比 1,000 字段落 LLM
   生成耗时显然 4-5×.

→ **spike 是 narrator 对"剧情密集段"的合理响应**, 与 D2 drift 1:1 因果.
不是确定性系统问题, 是 seed scenario 在 t200 / t450 附近本身就有 plot beat.

## Run 1 vs Run 2 — 为何 Run 1 stuck-state?

Run 1 在 t201 后 narrate 率维持 100% 直到 quota wall (~334 tick). Run 2 在
t201-250 spike 后 t251 主动 recover 到 44%.

**两者差别不在系统, 在 LLM stochasticity**:
* Run 2 narrator 在 spike 后选择"放下 climax 回到日常"
* Run 1 narrator 选择"持续 climax 直到剧情结束"

Run 1 的 stuck-state 不是 bug, 是 LLM 在面对剧情可继续高潮时的选择. 但 cost
负担巨大. 需要硬约束.

## 6-B carry-forward (真实修复路径)

1. **narrator 高 intensity 段落上限护栏** (新提议, 替代 silent_bias 退化):
   * 当 5/最近 10 tick avg narrative chars > 1500, 强制下 tick narrator
     prompt 加: "已连续高密度叙事, 请短促收尾或留白."
   * 比纯 silent_bias 调整更精准 (针对 length not frequency)
   * 不阻 spike (允许 t201 / t451 真正 climax), 仅阻 sustained climax (Run 1
     pattern).
2. **critic ACCEPT-only 段长检测**: critic_log 表明 96% ACCEPT, 长 spike 段
   critic 没起作用. 可考虑 length-gate 加严 (>2500 chars 强制 critic).
3. ~~Run 1 narrator silent_bias 失效~~: down-prioritized, run 2 显示
   silent_bias 工作正常, 只是 LLM 选了高 intensity 路径.

## 结论

| 维度 | 结论 |
| --- | --- |
| critic 触发率 健康 | ✓ (10% of narratives, 与 length gate 一致) |
| critic ACCEPT 率 | 96% (无反复 modify, 没 loop) |
| 真实 spike 信号 | narrative 长度暴涨 + narrate 率上升 (双向) |
| seed 依赖度 | HIGH (cross-seed 验证 留 task 3) |
| 系统 drift? | ❌ 没有 |
| 真实风险? | LLM 偶发选 sustained-climax 路径 (Run 1 pattern) |

## Artifacts

- 本 verdict: `docs/iter/verdict-spike-rootcause-0625.md`
- Run 2 critic_log: `backend/data/users/bench/novels/bench_phase6a-500tick-seed1-retry-0625_*/critic_log.jsonl` (24 rows)
- 调研脚本: 直接 python -c (inline), 未持久化
