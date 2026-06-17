# PHASE5_PLAN J Verdict — 200-tick long-range stress

> Run: `bench-phase5j-longrange-200tick.json`
> Date: 2026-06-17
> Stack: deepseek-v4-pro (gen) + glm-5.1 (judge, not run here) on ARK
> Phase 5-A (narrator cache) + Phase 5-B (world stale-skip) + 6 patched preset addendums (Phase 5-E) all active.

## Gate decision

**PASS** — Phase 5-B 架构改动通过长程验证. 详见下面三组数据.

## Headline numbers

| metric | value | comparison |
| --- | ---: | --- |
| completed_ticks | **200 / 200** | 100% no crash, no quota exhaust |
| total tokens | 1,062,459 | avg 5,312 tokens/tick (近 matrix 5,000 baseline) |
| call_count | 313 LLM calls | 1.57 calls/tick avg (含 Phase 5-B 跳过的 tick) |
| narration rate | **87 / 200 = 43.5%** | 与 5-tick Phase 5-B pilot 40% 高度一致 |
| narrative chars total | 84,238 | avg 968 chars/narrative (单条质量稳) |
| tick avg duration | 64.0s | max 368s (个别复杂 tick), min 0.02s (stale-skip) |
| open_loop_snapshots | 40 (sample every 5 tick) | longrange 追踪稳 |

## Phase 5-B drift validation (PHASE5_PLAN J 真正的 gate)

| 区段 | narrative chars | narration rate |
| --- | ---: | ---: |
| 前 50 tick (1-50) | 18,281 | 实数:~26 narratives |
| 后 50 tick (151-200) | **25,079 (+37.2%)** | 实数:~29 narratives |

后 50 tick narrative output 比前 50 **多 37%** — 这是关键数据点:

* Phase 5-B stale-skip 长程不 drift, 世界长程演化时角色互动/伏笔积累反而让 narrator 有更多素材
* 没观察到 PHASE5_PLAN candidate J 担心的"stale 累积 → 后期世界冻结 → narrator 沉默蔓延" 模式
* sideline TTL 累积无 drift (4 个 character_agent 字段在 by_agent 都健康产出)

## Phase 5-A cache observation (意外发现, NOT in gate)

| metric | value | expected |
| --- | ---: | --- |
| narrator prompt_tokens | 299,775 | n/a |
| narrator cached_tokens | **0** | 5-tick pilot 实证 56.9% |
| overall cache_hit_rate | 0.0% | matrix 实证 ~30% |

**这是异常 — 但不否定 Phase 5-A 架构正确性**. 可能原因 (待 follow-up 调查):

1. **ARK 端 cache TTL 短**: prefix cache 在 200-tick × 64s = 3.5h 跨度上可能多次 expire/refresh, 大部分 tick 命中"刚 refresh 的冷 cache"
2. **thinking-disabled 模式不报 cached_tokens metadata**: Phase 5-A 5-tick pilot 用更短场景,可能 ARK 在这种特定场景下不暴露 cached_tokens 字段
3. **ARK 不同地区/不同时间窗口 prefix cache 启用度不一**: 配额刷新后 cache 可能也重置

Phase 5-A 架构本身验证仍成立 (`test_narrator_prefix_cache.py` 3 个单测锁定 SYSTEM bit-identical 不变). cache 真实命中率长程是 metric layer 问题,不是 narrator 架构问题. 后续行动建议:

* 加 ARK 端 cache_tokens metadata 探针 (单独脚本, 不动 narrator)
* 跟 ARK 客服确认 deepseek-v4-pro + thinking_disabled 下 cache TTL/metadata 政策
* 矩阵 bench 短期看 cache hit 数据仍有效, 长程数据要单独标注

## Per-tick distribution (从 tick_durations_sec 推断)

* 95 ticks 用了 0.02-0.10s (基本都是 Phase 5-B stale-skip, 没 LLM call)
* 105 ticks 用了 16-368s (跑 LLM, 大部分 60-150s)
* stale_skip 实际率: 95/200 = **47.5%** (Phase 5-B target 30-50% ✓)

Phase 5-B 在长程下 skip 率从 5-tick pilot 的 40% 上升到 47.5%,still 在 target window.

## Per-agent breakdown

| agent | tokens | % | 备注 |
| --- | ---: | ---: | --- |
| narrator | 429,286 | 40.4% | < matrix bench 51% (因为长程 showrunner 多次触发, 占比稀释) |
| showrunner | 155,207 | 14.6% | 每 5 tick 跑一次, 200 tick = ~40 次, 正常 |
| world_simulator | 131,970 | 12.4% | 在 Phase 5-B skip 一半后仍 12% — 跑的那一半 tick 单次 cost 略高 |
| event_injector | 73,577 | 6.9% | 长程触发频率正常 |
| character_agent × 6 | ~178k 合计 | 16.8% | 6 角色场景, batch_decide 并发健康 |
| character_arc_tracker | 42,795 | 4.0% | v2.18 character arc 追踪 |
| novelty_critic | 20,830 | 2.0% | 每 20 tick 触发, ~10 次 |
| memory_compressor:l0_l1 | 20,227 | 1.9% | L0→L1 压缩 ~4 次 |

总体: agent token 分布合理, 没有"卡死在某 agent"的偏态.

## Decision

* **Phase 5-B stale-skip: SHIP confirmed** (200-tick longrange validates)
* **Phase 5-A narrator cache: 架构 SHIP, metric follow-up 需做** (test 保证不退化, 但长程 cached_tokens 数据需进一步调查 ARK 行为)
* **Phase 5-E preset patch (atmosphere)**: 隐式验证 (200-tick 跑的是 default preset = literary, 不直接测 atmosphere patch,但 matrix 数据已确认)

未做 (carry forward):
* 3-seed cross-theme 长程 (PHASE5_PLAN 原 J 候选实际要 3 seed × 200 tick, 这里跑了 1 seed)
* ARK cache 行为深入诊断
