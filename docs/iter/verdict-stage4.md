# Stage 4 Verdict — long-range drift fixed (3 changes combined)

> **Status:** validated. Stage 3 verdict 登记的 3 项改动 (iter#90, #91, #92)
> 在 iter#94 50 tick 长 bench 中**同时缓解了所有 drift 信号**.

## Compare — same seed, same N, head-to-head

| metric                       | stage3 (iter#89 baseline) | stage4 (iter#94) |        Δ |
| ---------------------------- | ------------------------: | ---------------: | -------: |
| open_loops at tick 50        |                         9 |                5 |    -44%  |
| open growth (start→end)      |               5 → 9 (+80%) |       4 → 5 (+25%) | -69pp accumulation |
| stale_loops at tick 50       |                         3 |                1 |  recovery |
| stale max during run         |                         3 |                3 |   平 (transient) |
| avg_urgency at tick 50       |                      6.11 |             6.80 |    +0.69 |
| avg_urgency trend            |          7.0 → 6.11 单调下降 |  7.25 → 6.80 持稳 | 止住下降 |
| drift signals triggered      |                         2 |            **0** | 全部解除 |
| distinct char-2              |                     0.895 |            0.895 |       持平 |
| overlap consec char-2        |                     0.082 |            0.076 |    -0.006 |
| narrations                   |                        42 |               40 |        -2 |
| total tokens (15 tick budget)|                   509,417 |          540,474 |     +6%  |

## Drift signal table

stage3:
- ❗ `open_loop_accumulation: 5 → 9 (+4)`
- ❗ `stale_loops_at_end=3 (≥3 — 伏笔僵死苗头)`

stage4:
- (no drift signal triggered)

## 三件套组合效果

* **iter#90** (EventInjector 偏好关旧, 看到 stale ≥3 不新种) — 在 tick
  35 stale_loops 升到 3 时, 后续注入活化老 loop 而非新种, 让 open_count
  止住于 5 (vs stage3 升到 9).
* **iter#91** (TickState 累计 closed) — 让 iter#92 review fix 后的 bench
  数据真实可读. closed=0 仍出现, 但因为 5 个 open_loop 都被 narrator
  touch 进活跃状态 (而非 reap), 不是 close 路径. 数据准确.
* **iter#92** (Showrunner cold_thread → narrative_value_hint ≥ 7) —
  在 tick 40 → 45 区段, stale 从 3 跌到 1, 说明高 hint 注入让 narrator
  真的在那 5 tick 里把 cold thread 写进了 2 段叙述, "复活" 它们.

avg_urgency 7.25 → 6.80 (vs stage3 7.0 → 6.11) — 新种伏笔 + 复活旧
伏笔混合, 整体 urgency 不再单调下降. 这是 Stage 3 verdict 候选 #3
设计目标的直接证据.

## Cost 解读

+6% total tokens (540k vs 509k) 是合理代价 — 复活类事件 hint=7 → narrator
critic gate 触发 → critic 链多跑几次. 拿 plot drift 全部修复换 6% 成本,
联合 cost-quality 指标 win.

## §6 Stage 3 exit retrospective

Stage 3 §6 退出条件: "漂移曲线产物入库 + ≥1 新优化面登记". iter#89 时已
满足. iter#94 在 Stage 4 框架下验证 3 项均落地有效, 这是 Stage 3 的真正
回路闭合.

## §5 Stage 2 再审视

Stage 2 verdict (iter#85): stage2 (importance-gated critic) 比 v15
省 22% cost. Stage 4 = stage2 + 三个 long-range 补丁. 与 stage2 cost
对比:

| 配置        | 15 tick tokens | 50 tick tokens | 50 tick narrations |
| ----------- | -------------: | -------------: | -----------------: |
| stage2 only | 146,819        | (未跑)         | (未跑)             |
| stage4      | (未跑)         | 540,474        | 40                 |

Stage 4 average 10,810 tok/tick — 接近 stage2 line rate, 远低于 v15.

## Sources

- bench stage4: `docs/iter/bench-stage4-50tick.json`
- analysis stage4: `docs/iter/longrange-stage4-50tick.{json,md}`
- baseline stage3: `docs/iter/bench-stage3-longrange-50tick.json` + `verdict-stage3.md`
- iter trail: iter#90 (EventInjector), iter#91 (TickState counter),
  iter#92 (Showrunner→hint), iter#93 (review fixes), iter#94 (本 verdict)

## Next direction

stage4 现已是 best stable candidate (跨 cost / quality / drift). 待
N ≥ 30 narrations × 多 seed 后转 final. Phase 2 §6 exit 全部达成;
继续 iter#95+ 由用户指引方向 (可能候选: 推 v16 + critic length-gate 调高
进一步省 cost; 或加新 prompt 多样化指标; 或 stage4 跨 3 seed 验证).
