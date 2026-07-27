# docs/iter/ INDEX

> 787 件 artifact. 本 index 按用途分类, 给新读者一个清晰起点.
> 最新更新: 2026-06-25 (Phase 6-B/C iter A-V batch).

## 2026-07-22 验收

* [Event Completion Repair](event-completion-repair-20260722.md) — 24/24 离线通过；真实小矩阵 9/15，结论 `EVENT_REPAIR_FAIL`，后续阶段未运行。
* [Section Balance Control](section-balance-control-20260726.md) — Budget + Ending Gate + COMPACT；离线 24/24、6/6，真实 Mini 8/15，结论 `SECTION_BALANCE_FAIL`，45 节 Stage 1 未运行。
* [Writer First-Pass Optimization](writer-first-pass-optimization-20260727.md) — Preflight + 单次 Retry + Revision Guard；真实 Mini 11/15、初稿直通 3/15，结论 `WRITER_FIRST_PASS_FAIL`。

## 起步阅读顺序

1. [STATUS.md](STATUS.md) — rolling 状态板, 一眼看当前进展
2. [ITERATION_LOG.md](ITERATION_LOG.md) — 全程时间线 + 每 iter 一行
3. 当前 Phase: [PHASE6_PLAN.md](PHASE6_PLAN.md)
4. 最新 verdict: [verdict-phase6a-500tick-retry-0625.md](verdict-phase6a-500tick-retry-0625.md)

## Phase plans (策划)

| phase | 计划 | 结案 |
| --- | --- | --- |
| Phase 3 | [PHASE3_PLAN.md](PHASE3_PLAN.md) | [PHASE3_FINAL.md](PHASE3_FINAL.md) |
| Phase 4 | [PHASE4_PLAN.md](PHASE4_PLAN.md) | [PHASE4_FINAL.md](PHASE4_FINAL.md) |
| Phase 5 | [PHASE5_PLAN.md](PHASE5_PLAN.md) | [PHASE5_FINAL.md](PHASE5_FINAL.md) |
| Phase 6 (current) | [PHASE6_PLAN.md](PHASE6_PLAN.md) | (in progress) |

## Runbooks (实操手册)

* [PHASE6A_500TICK_RUNBOOK.md](PHASE6A_500TICK_RUNBOOK.md) — 500-tick stress bench 启停 + 6 drift signal 判读
* [PAIRWISE_JUDGE_RUNBOOK.md](PAIRWISE_JUDGE_RUNBOOK.md) — Phase 2 cross-seed mimo pairwise 评判流程
* [RECOMMENDED_PAIRS.md](RECOMMENDED_PAIRS.md) — Phase 5-D 推荐 theme×style 配对

## 最新 verdict (按时间倒序)

| 时间 | verdict | 关键信号 |
| --- | --- | --- |
| 2026-07-27 | [writer-first-pass-optimization-20260727.md](writer-first-pass-optimization-20260727.md) | Preflight + Retry + Revision Guard；真实 Mini 11/15、first pass 3/15，**WRITER_FIRST_PASS_FAIL** |
| 2026-07-27 | [section-balance-control-20260726.md](section-balance-control-20260726.md) | SectionBudget + Ending Gate + COMPACT；真实 Mini 8/15，**SECTION_BALANCE_FAIL** |
| 2026-07-26 | [section-length-control-20260726.md](section-length-control-20260726.md) | WritingPlan + guarded EXPAND；离线 24/24、6/6，真实 Mini 9/15，**SECTION_LENGTH_FAIL** |
| 2026-07-26 | [stage1-full-matrix-validation-20260726.md](stage1-full-matrix-validation-20260726.md) | 3 themes × 5 styles × 3 attempts，39/45 commit，**STAGE1_FAIL** |
| 2026-06-25 | [verdict-phase6a-500tick-retry-0625.md](verdict-phase6a-500tick-retry-0625.md) | 500/500 effective, 3.0M tokens, narrate% 48% baseline. **反驳 run 1 "drift" 假设** |
| 2026-06-25 | [verdict-spike-rootcause-0625.md](verdict-spike-rootcause-0625.md) | critic 96% ACCEPT, spike = narrative chars 暴涨 (plot beat 响应) |
| 2026-06-24 | [verdict-phase6a-500tick.md](verdict-phase6a-500tick.md) | 334/500 quota wall, CONDITIONAL PASS, 怀疑 narrate-rate 失控 |
| 2026-06-24 | [verdict-iter7-critic-log-stats.md](verdict-iter7-critic-log-stats.md) | Phase 6-C iter#7 data 栈三件套 |

## Bench JSON / MD pairs (按用途)

### Phase 6-A 长程 bench (500-tick)

* `bench-phase6a-500tick-seed1.{json,md}` — Run 1 (24 日, quota wall)
* `bench-phase6a-500tick-seed1-retry-0625.{json,md}` — Run 2 (25 日, clean exit)
* `bench-phase6a-500tick-republic-iterN.{json,md}` — 14:03 cron 起 (planned)
* `bench-phase6a-500tick-apocalypse-iterN.{json,md}` — 22:07 cron 起 (planned)

### Phase 5 长程探索 (50-tick / 200-tick)

* `bench-iter103-seed{1,2,3}-50tick.{json,md}` — Phase 5 baseline 3-seed
* `bench-phase5j-longrange-200tick.{json,md}` — Phase 5-J 长程 PASS
* `longrange-phase5j-*.{json,md}` — longrange 采样

### Phase 5-D theme × style matrix (208 个配对)

* `bench-m_{theme}_{style}.{json,md}` — 21 theme × 16 style 全矩阵
  * 例: `bench-m_ancient_romance_classical_chapter.{json,md}`
* `matrix-bench-{timestamp}.md` — matrix 跑后聚合 verdict
* `matrix-bench-retro-*.md` — retrospect 跑

### Phase 5 ARK 缓存探针

* `probe-ark-cache-*.json` — narrator prompt cache pilot
* `probe-ark-endpoints-1781688145.json` — endpoint metadata 验证

## Calibration 与 sample 研究

* [a1-calibration-iter-c2.md](a1-calibration-iter-c2.md) — A1 抽样 50 narratives, 验证 production avg=2.14
* [a1-calibration-iter-c3-post.md](a1-calibration-iter-c3-post.md) — iter#C3 dedup 后 -35% noise

## Drift analysis (长程 verdict 产物)

* [longrange-drift-phase6a-retry-0625.md](longrange-drift-phase6a-retry-0625.md) — Run 2 D1×2 spike, recover

## STATUS 快照 (历史)

* [STATUS.md](STATUS.md) — current
* [STATUS-iter120-pause.md](STATUS-iter120-pause.md) — iter#120 pause 节点

## 单 iter verdict 文件 (按 iter 号)

verdict-iter{N}-*.md 命名约定; 检索具体 iter 用 grep:

```bash
ls docs/iter/verdict-iter*.md | sort -t- -k2,2n
```

## 历史 phase 关键文档 (引用频次高)

* [PHASE3_FINAL.md](PHASE3_FINAL.md) — cast confound 实验, CLI opt-in 收档
* [PHASE4_FINAL.md](PHASE4_FINAL.md) — sideline default ON (+38.6pp mimo cross-seed)
* [PHASE5_FINAL.md](PHASE5_FINAL.md) — narrator prompt cache + theme×style preset

## 不在本 index 内

* 单纯实验 bench (verdict-iter1-XXX 之类) — 按 ITERATION_LOG 链接定位
* matrix bench 单个 cell (用 grep matrix-bench-{timestamp})
* probe-* JSON (只在 verdict 引用时打开)
