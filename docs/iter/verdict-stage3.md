# Stage 3 Verdict — long-range drift surfaced

> **Status:** complete (Stage 3 exit condition: 长程曲线产物入库 ✓,
> 新优化面登记 ≥ 1 项 ✓ — 实际登记 3 项).

## Run setup

- bench: `docs/iter/bench-stage3-longrange-50tick.json`
- ticks: 50
- narrations produced: 42
- total_tokens: 509,417 (≈ 10,200 / tick avg)
- config: stage2 default (CRITIC_IMPORTANCE_MIN=7 importance-gated)
- longrange sample interval: every 5 tick (10 samples)

## Foreshadowing trend (核心发现)

| tick | open | stale_open | avg_urgency |
| ---: | ---: | ---------: | ----------: |
| 5  | 5 | 0 | 7.00 |
| 10 | 6 | 0 | 6.67 |
| 15 | 7 | 0 | 6.43 |
| 20 | 8 | 0 | 6.25 |
| 25 | 8 | 2 | 6.25 |
| 30 | 8 | 1 | 6.25 |
| 35 | 8 | 2 | 6.25 |
| 40 | 9 | 3 | 6.11 |
| 45 | 9 | 3 | 6.11 |
| 50 | 9 | 3 | 6.11 |

* open_loops 单调增长 **5 → 9 (+80% 容量)**
* stale_open (>20 tick 无推进) **0 → 3** by tick 40
* avg_urgency 单调下降 7.0 → 6.11 — 新注入伏笔越来越弱
* closed_count 暂未追踪 (iter#89+ 补)

## Drift signals triggered

1. **open_loop_accumulation: +4** — Phase 2 §6 真正想抓的失败模式之一.
2. **stale_loops_at_end=3** — 伏笔僵死苗头.

## Repetition (det)

42 段全程聚合:
* distinct char-2/3/4: 0.895 / 0.979 / 0.996 (与短 bench 持平)
* overlap consec char-2: 0.082 (仍然低)

**结论: prose-level 套路化指标 OK; 但 plot-level (伏笔簿记) 已出问题.**

## Novelty trend

samples=0 — `novelty_records` 字段在 iter#87 reviewed 是 placeholder,
iter#90+ 接 NoveltyCriticOutput 回调.

## §6 退出 + 新优化面登记

§6 退出: "漂移曲线产物入库 ≥ 1 项已登记". 入库 ✓, 登记 3 项:

### iter#90 候选 — EventInjector 偏好关旧伏笔

当前 EventInjector 不考虑 open_loop 容量, 高 stale 时仍新种. 改造方向:
* 注入决策时读 stale_open 数 (orchestrator 已有数据), > 阈值时不再
  新种, 优先生成"激活已有 cold thread" 的事件
* Showrunner 已识别 cold thread, 但 inject 阶段不消费. 接通 →
  predicted improvement: open_count 不再单调增长.

### iter#91 候选 — TickState 加 `_loops_closed_total` 累计

让 Stage 3 bench 后续能算 open/closed ratio. 现在 ratio 字段写 0
是不真. orchestrator `reap_stale_open_loops` 已有回收路径,
加 counter 5 行代码改造.

### iter#92 候选 — Showrunner 把 urgency boost 写进 inject 建议

avg_urgency 单调下降意味着新伏笔越来越弱. Showrunner cold_thread
output 应当强 urgency. inject 时尊重这个 urgency 而非默认 5-6.

## Sources

- bench: `docs/iter/bench-stage3-longrange-50tick.{json,md}`
- analysis: `docs/iter/longrange-stage3-50tick.{json,md}`
- iter trail: iter#86 (reducers), iter#87 (bench instrument),
  iter#88 (review fixes), iter#89 (实跑 + 本 verdict)
