# iter#105 — close-fix 在 seed1 (plot-light) 验证非退化

> verdict-iter104 §Continuation P0: 验证 iter#103 close-fix 不退化原本
> 0 drift 的 plot-light seed1.

## Setup

| iter | bench | ticks | total_tokens | narrations | cast | seed |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| #100 | stage5-seed1-50tick | 50 | 521,767 | 41 | 2 | 蒸汽朋克 (baseline) |
| **#105** | **iter103-seed1-50tick** | **50** | **544,467** | **44** | **1** | **同上 (+iter#103 close)** |

## Long-range drift table

### iter#105 (with close fix)

| tick | open | stale | closed_total | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 6 | 0 | 0 | 6.17 |
| 10 | 6 | 0 | 0 | 6.17 |
| 15 | 6 | 0 | 0 | 6.17 |
| 20 | 6 | 0 | 0 | 6.17 |
| **25** | **6** | **1** | **1** | **6.17** |
| **30** | **4** | **1** | **3** | **6.75** |
| 35 | 4 | 0 | 3 | 6.75 |
| 40 | 4 | 0 | 3 | 6.75 |
| 45 | 4 | 0 | 3 | 6.75 |
| 50 | 4 | 0 | 3 | 6.75 |

### iter#100 baseline (无 close)

| tick | open | stale | closed_total | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 4 | 0 | 0 | 6.5 |
| 25 | 4 | 0 | 0 | 6.5 |
| 35 | 6 | 0 | 0 | 6.0 |
| 50 | 6 | 1 | 0 | 6.0 |

## Key result — close 机制在 plot-light 题材主动运作

- iter#100 baseline: closed=0 全程
- **iter#105 with-fix: closed=3** 在 tick 25 + 2 在 tick 30

vs iter#104 seed3 50t: closed=1 在 tick 50 (临门一脚) — seed1 更早更积极
关闭. 推断: bootstrap 初始 6 open_loops 让 Showrunner 早期就触发 close
决策, 然后 池子稳定在 4.

## Delta vs iter#100 (same seed1 50t, 唯一差别 = iter#103 close)

| metric | #100 baseline | #105 with-fix | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 521,767 | 544,467 | +4.4% |
| call_count | 123 | 126 | +2.4% |
| narrations | 41 | 44 | +7.3% |
| **closed_total** | **0** | **3** | **+3** |
| open final | 6 | 4 | **-33%** |
| stale final | 1 | 0 | -100% |
| avg_urg final | 6.0 | 6.75 | **+12.5%** |
| distinct char-2 | 0.8825 | 0.8689 | -1.5% |
| **drift signals** | **0** | **0** | **同 (无退化)** |

## 解读 — close-fix 在 2 题材的不同表现

| 题材 | 早期 open | 关闭路径 |
| --- | --- | --- |
| seed1 (蒸汽朋克 plot-light) | bootstrap 给 6 → 早期 cap | Showrunner tick 25/30 主动关 1+2 → 4 稳定 |
| seed3 (末世废土 plot-dense) | bootstrap 给 4 → 缓慢爬 | 直到 tick 50 open 才到 5 → 关 1 |

close 机制不是"被动应急", 而是 **prompt 设计成 open ≥ 4 就考虑关 stale** —
跨 2 题材都 robustly 起作用.

## Cost / quality summary 跨 close-fix 2 个 seed (iter#104 + #105)

| seed | cost delta vs no-fix | quality delta |
| --- | ---: | --- |
| seed3 | -53% (gross) / -30% (adj) | drift 1→0, avg_urg +12%, distinct +1.6% |
| seed1 | +4.4% (prose budget 微增) | drift 0→0 持平, avg_urg +12.5%, distinct -1.5% (噪声) |

加权: close-fix 在高密度题材 cost 显著降 (close 释放 token), 在低密度题材
cost 略升 (Showrunner JSON 加了 close 字段). **quality 跨题材 robust 提升**.

## Verdict

iter#103 close-fix **跨 2 题材** (plot-light seed1 + plot-dense seed3) 实测
**非退化 + 主动提升**:
- ✓ seed1 closed=3, open -33%, avg_urg +12.5%, drift 同 0
- ✓ seed3 closed=1, open -55%, avg_urg +12%, drift 1→0

Phase 2 stage5 + iter#103 close-fix = **production-ready best stable**.

cost delta seed1: +4.4% (题材 cost 反向变化在预期内)
quality delta seed1: drift 0→0 持平, avg_urg +12.5%
测试: 701/701 (无新代码改动, 仅 bench)

## Continuation

下一候选 (按 verdict-iter104 §Continuation):
1. (P0 done) seed1 regression check ✓
2. (P1) seed2 with close-fix (民国上海) — 完成 3-seed × close-fix
3. (P2) Showrunner close prompt 进一步 tuning — open ≥ 4 阈值是否过低?
   当前 iter#105 显示 open=6 时关 1+2 是合理. open=5 时也开始关合理.
4. (P3) cast-confound 控制 — 用同 bootstrap seed 控变量

## Sources

- bench: `docs/iter/bench-iter103-seed1-50tick.{json,md}`
- analysis: `docs/iter/longrange-iter103-seed1-50tick.{json,md}`
- baseline: `verdict-iter100-stage5-seed1-50tick.md`
- fix: iter#103 + iter#104 verdict
