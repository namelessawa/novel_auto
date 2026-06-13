# iter#143 — Phase 4-E 首次 positive 信号 (sideline 66.67% mimo win)

> Phase 4-E (iter#139-142) infrastructure 完成, iter#143 mimo pairwise 给出
> 首次 quality 评估. 结果与 iter#133-135 (静态 cast=3) 反向 — 动态 sideline
> 在 mimo 看起来**改善** prose.

## Setup

| iter | bench | sideline 行为 | chars (bootstrap) | tokens |
| --- | --- | --- | ---: | ---: |
| #140 | iter140-seed1-sideline-active | infrastructure 在, 0 触发 | 5 | 540,109 |
| **#142** | **iter142-seed1-sideline-mandatory-r** | **strengthened prompt 触发 char_limou tick 5-30** | **8** | **566,526** |

mimo pairwise: #140 (v15) vs #142 (v16), 10 pairs, 50k budget.

## Verdict

**v16_promote (provisional=False)**: v16 win-rate 66.67%, ≥ 45% threshold.

| dim | v15 (no sideline) | v16 (sideline triggered) | delta |
| --- | ---: | ---: | --- |
| pairwise win | 33.33% | **66.67%** | **2x 倍率 v16 胜** |
| tie | 0% | 0% | — |
| parse_err | 0 | 1 | 1 |
| distinct char-2 | 0.8643 | 0.8739 | **+1.1%** |
| distinct char-4 | 0.9904 | 0.992 | +0.16% |
| overlap consec char-2 | 0.0983 | 0.0921 | **-6.3%** (less repetition) |
| narrations | 41 | 41 | 同 |

## 与 iter#133-135 静态 cast=3 反向对比

| 实验 | quality 效果 | 解读 |
| --- | --- | --- |
| iter#133-135 静态 cast=3 (1A+2B+0C 固定) | mimo 33% win, 退化 | cast 永远只 3 chars, character interaction 单调 |
| **iter#143 动态 sideline (cast wide + 选择性 sideline)** | **mimo 66.67% win, 改善** | **sideline 仅暂时让"无贡献" char 退场, 池子保留, 后续可恢复** |

**关键差别**: 静态 cast 限制 interaction 多元性 (永远缺), 动态 sideline 仅当
char 实际"冷场" 时退场 (有需要时回来). Showrunner 看 arc_progress 选 sideline,
不是机械减 cast.

## Confounds 注意

- chars 5 vs 8 (wide range LLM 随机) — 不是 clean A/B. v16 cost +4.9% 可
  能主要因 chars 多.
- 1 parse_err / 10 pair — mimo 有 1 个判定无效, 实际 sample 是 9.
- 单 seed — 跨题材稳定性待 iter#144+ 验证 seed2/3.

## cost-quality 双指标

| metric | v15 (#140) | v16 (#142) | delta |
| --- | ---: | ---: | --- |
| tokens | 540,109 | 566,526 | +4.9% (chars confound) |
| mimo pairwise win | 33.33% | **66.67%** | **+33pp** |
| distinct char-2 | 0.8643 | 0.8739 | +1.1% |
| drift signals | 0 | 0 | 同 |

**初判**: Phase 4-E **quality positive**. cost 中性 (净 +5% confounded). 后续
iter#144+ 跑 controlled cast count 同 cast 数实验. 如 quality 维持 +30pp,
Phase 4-E **可以 production landing**.

## Phase 4 status (post-iter#143)

| 候选 | 状态 | 信号 |
| --- | --- | --- |
| **E) Showrunner runtime sideline** | **infrastructure ✓ + 首次 positive (#139-143)** | **quality +33pp 待跨题材验证** |
| F) critic prompt cache | 未启动 | 低成本 探索 |
| G) compressor budget | 未启动 | 与 D 组合 |
| D) memory fidelity | 未启动 | 高成本 |

## Continuation

iter#144+ 候选:
1. (P0) Phase 4-E controlled experiment — 固定 cast (e.g., --cast 2A+2B+1C),
   开/关 sideline 各 1 bench → 真正 isolation
2. (P1) seed2 + seed3 mandatory sideline bench → 跨题材一致性
3. (P2) F (critic cache) 探索

## Sources

- pairwise: `verdict-iter143-sideline-active-vs-mandatory.{json,md}`
- v15 bench: `bench-iter140-seed1-sideline-active.json`
- v16 bench: `bench-iter142-seed1-sideline-mandatory-r.json`
- 静态 cast=3 反向对比: `verdict-iter133-cast3-pairwise-contradiction.md`
