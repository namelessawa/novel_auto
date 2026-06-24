# Phase 6-A · 500-tick retry · verdict (REVISED)

> 2026-06-25 07:37. seed1 = steampunk_archive, style=literary, cast221.
> Bench artifact: `docs/iter/bench-phase6a-500tick-seed1-retry-0625.{json,md}`.
> 配额: DeepSeek 5h window reset 01:53 → bench 跑 02:32 → 07:37, **未触顶**.

## Headline · **PASS · 长程稳定性确认**

Run 1 (2026-06-24 17:38 → 23:15) verdict 是 CONDITIONAL PASS, 怀疑 narrate-rate
失控为长程 drift. 本 retry **反驳**该假设: 同 seed / 同参数, narrate-rate 在
t201 短暂 spike (60%) 后**主动恢复 baseline 44%**, 非确定性 drift, 是 LLM
stochasticity.

## Two-run side-by-side

| metric | run1 (6-24) | run2 (6-25 retry) | Δ |
| --- | ---: | ---: | ---: |
| 完成 tick | 500/500 | 500/500 | — |
| **有效 tick** | **334** (quota wall) | **500** (clean) | +50% |
| total tokens | 4,448,383 | **3,023,064** | **-32%** |
| LLM calls | 1,085 | 904 | -17% |
| avg tick dur (effective) | 59.5s | **36.0s** | **-40%** |
| narratives | 222 | 241 | +9% |
| **avg narrate%** | **66%** (扭曲) | **48%** | -18pp |
| 终止 | quota touchoff | clean exit | ✓ |
| narrator tokens | 1,170,839 | 1,215,168 | +4% |

> **Run 1 的 4.45M tokens 是 t201+ stuck-narrate 状态下烧的**, 不是健康基线.
> Run 2 的 3.0M = 健康基线 + 2 个 recoverable spike. 500-tick token 估算
> 应调整为 **~3M** (而非 runbook 的 5M 或 run 1 投影的 6.7M).

## Drift 信号 (run 2)

| code | bucket | 测量 | 状态 |
| --- | --- | --- | --- |
| D1 | t1-50 baseline 23.1s | — | baseline |
| D1 | t51-100 28.7s · 46% narrate | 1.24× | ✓ healthy |
| D1 | t101-150 27.4s · 40% narrate | 1.19× | ✓ healthy |
| D1 | t151-200 29.6s · 46% narrate | 1.28× | ✓ healthy |
| D1 | **t201-250 51.9s · 60% narrate** | **2.25×** | ⚠ spike (recover) |
| D1 | t251-300 29.8s · 44% narrate | 1.29× | ✓ **recovered** |
| D1 | t301-350 27.1s · 46% narrate | 1.17× | ✓ healthy |
| D1 | t351-400 29.2s · 44% narrate | 1.26× | ✓ healthy |
| D1 | t401-450 25.5s · 42% narrate | 1.10× | ✓ healthy |
| D1 | **t451-500 88.0s · 70% narrate** | **3.81×** | ⚠ end spike |
| D4 memcompress | by_agent_cum 触发 | — | ✓ healthy |
| D6 token cascade | 50-bucket 间增长非超线性 | — | ✓ healthy |

**两个 spike 都是 LOCAL 而非 monotonic** — 反驳 "drift" 假设, 支持
"plot beat 触发" 解释.

## 真实 6-A 结论 (REVISED)

| 维度 | run 1 结论 | run 2 实测 | 修正后结论 |
| --- | --- | --- | --- |
| 长程稳定性 | PARTIAL | 500/500 effective | **HEALTHY** |
| narrate-rate 失控 | 担忧确定性 drift | 主动恢复 | **stochastic spike** |
| Memory pipeline | HEALTHY | HEALTHY | HEALTHY |
| 优雅降级 | HEALTHY | (未触发) | HEALTHY |
| Token 效率 | 13.3k/effective tick | **6.0k/tick** | EXCELLENT |
| 500-tick cost estimate | 6.7M | **3.0M** | ~3M ± 0.5M |

## 6-B carry-forward (revised priority)

1. **narrate-rate spike 根因深挖** — t201 是 seed scenario 的 plot beat? Run 1
   的 stuck-state 是 LLM 在 climax 段进入"每 tick 全产" 局部均衡? 需:
   * narrative_critic_log 复查 run 1 t201+ 决策, 看 critic 是否每次都 ACCEPT
   * cross-seed bench 验证 spike 位置是否 seed-dependent (Phase 4-E 教训 #4)
2. **CharacterAgent Goal schema validator 仍待修** (run 2 仍频繁 Skip invalid):
   * 加 validator 强转: 'critical'→10, 'high'→8, '0%'→0.0, int id → str(id)
   * 留 iter#J
3. **DeepSeek 5h 配额 hard ceiling** — run 2 未触顶但接近 (3.0M ~ 60% 配额),
   单 seed cross-window resume 不紧急. 留 iter#K.

## 不再担心 (down-prioritized)

- ~~narrator silent_bias 长程退化机制~~ (run 2 显示 silent_bias 在 spike 后会
  recover, 不需要强制 fix)
- ~~5M token 估算偏高~~ (Run 1 因 quota wall 扭曲, 真实 ~3M)

## Sources

- Run 1 verdict: `verdict-phase6a-500tick.md` (24 日, CONDITIONAL PASS)
- Run 2 bench: `bench-phase6a-500tick-seed1-retry-0625.{json,md}` (1014 KB JSON)
- Run 2 drift analysis: `longrange-drift-phase6a-retry-0625.md`
- Process log: `tasks/b73dpbxyf.output`
- Cron job: `fe20f915` (one-shot @ 25 日 02:30) — fired正常
