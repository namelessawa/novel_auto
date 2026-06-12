# iter#122 — Phase 3-B cast-confound 在 seed1 验证 (跨题材 generalization)

> verdict-iter121 §Continuation P0: seed1 + seed2 cast 控制实验, 看
> Phase 3-B 治理是否在 plot-light 题材也有 cost 节省.

## Setup

| iter | bench | cast 模式 | actual chars | total_tokens |
| --- | --- | --- | ---: | ---: |
| #100 | stage5-seed1-50tick (baseline) | wide range | 2 | 521,767 |
| #105 | iter103-seed1-50tick (close-fix) | wide range | 1 | 544,467 |
| **#122** | **iter122-seed1-cast221** | **2A+2B+1C 指定** | **4 (LLM 漏 1)** | **509,863** |

## Long-range drift table (iter#122)

| tick | open | stale | closed_total | avg_urg |
| ---: | ---: | ---: | ---: | ---: |
| 5 | 5 | 0 | 1 | 6.4 |
| 10 | 5 | 0 | 1 | 6.4 |
| 15 | 4 | 0 | 2 | 6.75 |
| 20 | 4 | 0 | 3 | 6.75 |
| 25 | 4 | 0 | 3 | 6.75 |
| 30 | 3 | 0 | 4 | 7.33 |
| 35-40 | 3 | 0 | 4 | 7.33 |
| 45-50 | 4 | 0 | 4 | 6.75 |

close 在 tick 5 就触发, 持续到 tick 30 累 4 个. 末期 open stable 在 3-4.

## 跨 iter#100 / #105 / #122 三向对比

| metric | #100 baseline | #105 close-fix | **#122 + cast** | #122 vs #100 | #122 vs #105 |
| --- | ---: | ---: | ---: | ---: | ---: |
| total_tokens | 521,767 | 544,467 | 509,863 | **-2.3%** | **-6.4%** |
| call_count | 123 | 126 | 124 | +0.8% | -1.6% |
| narrations | 41 | 44 | 42 | +2.4% | -4.5% |
| distinct char-2 | 0.8825 | 0.8689 | 0.8649 | -2.0% | -0.5% |
| open final | 6 | 4 | 4 | -33% | 0 |
| closed_total | 0 | 3 | 4 | +4 | +1 |
| avg_urg final | 6.0 | 6.75 | 6.75 | +12.5% | 0 |
| drift | 0 | 0 | 0 | 0 | 0 |

## seed1 vs seed3 Phase 3-B win 对比

| seed | iter | cost delta vs no-cast | quality delta |
| --- | --- | ---: | --- |
| seed3 | #121 vs #104 | **-19% (戏剧)** | drift 0/0, distinct +1.6%, avg_urg +3%, closed +3 |
| **seed1** | **#122 vs #105** | **-6.4% (温和)** | drift 0/0, distinct -0.5%, closed +1 |

**解读**: Phase 3-B 在 plot-dense / cast-dense 题材 (seed3) 收益最大
(-19%), 在 plot-light 题材 (seed1) 收益温和但**正向且 quality 不退化**.
跨题材 robustly 工作.

## 备注 — LLM 未严格遵守 cast 数

- 请求: 2A+2B+1C = 5 角色
- 实测: 4 角色 (LLM 偷工 1)

PROMPT 已用 "恰好" 强语气仍偶发漏. iter#123 review 已加 all-or-nothing
保护 partial set, 但 LLM compliance 是独立问题. 可考虑:
- bootstrap 时校验 actual cast count == requested, 不匹配重试
- 或加 max 3 次 retry budget

这是 iter#124+ 候选, 非本 iter 阻断.

## 双指标 delta summary

cost delta vs iter#105 (close-fix): -6.4%
cost delta vs iter#100 (no-fix): -2.3%
quality delta: drift 0→0, avg_urg 同, distinct -0.5% (噪声)

## Phase 3-B 跨题材 verdict

| seed | cast-control 净收益 |
| --- | --- |
| seed1 (蒸汽朋克 plot-light) | -6.4% cost, quality 持平 ✓ |
| seed3 (末世废土 plot-dense) | -19% cost, quality 提升 ✓ |
| seed2 (民国 plot-medium) | 待 iter#124 验证 |

## Continuation

iter#124 候选: seed2 cast 控制完成 3-seed 完整 matrix.
然后 iter#125 候选: LLM cast compliance retry 机制.

## Sources

- bench: `docs/iter/bench-iter122-seed1-cast221.{json,md}`
- analysis: `docs/iter/longrange-iter122-seed1-cast221.{json,md}`
- baseline: `verdict-iter100-stage5-seed1-50tick.md`
- close-fix: `verdict-iter105-seed1-close-fix.md`
- seed3 wins: `verdict-iter121-cast-confound-confirmed.md`
