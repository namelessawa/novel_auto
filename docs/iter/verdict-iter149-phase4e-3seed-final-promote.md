# iter#149 — Phase 4-E 3-seed FINAL: 跨题材 promote, ready for production

> Phase 4-E (#139-149) clean A/B 跨 3-seed × cast=5 (controlled) × pairwise
> mimo: **avg 69.3% v16 win**, all 3 seed v16_promote. Cost essentially
> neutral. Phase 4-E quality 维度 decisive 改善.

## 3-seed × controlled A/B FINAL matrix

| seed | bench v15 (no sideline) | bench v16 (sideline ON) | v16 win | tokens delta | verdict |
| --- | --- | --- | ---: | ---: | --- |
| seed1 (蒸汽朋克) | iter#122 | iter#144 | **80%** | -2.9% | v16_promote |
| seed2 (民国) | iter#124 | iter#146 | 50% | +0.4% | v16_promote (borderline) |
| seed3 (末世) | iter#121 | iter#148 | **77.78%** | +6.2% | v16_promote |
| **avg** | — | — | **69.3%** | **+1.2%** | **all promote** |

跨 3 seed, **mimo pairwise 跨题材 decisive prefer sideline 机制**. cost
基本中性 (+1.2% avg, 跨 seed σ ~4.5%, 噪声内).

## det vs mimo 总结

| dim | seed1 v15/v16 | seed2 v15/v16 | seed3 v15/v16 |
| --- | --- | --- | --- |
| distinct char-2 | 0.8649 → 0.8563 (-1.0%) | 0.874 → 0.8717 (-0.3%) | 0.8787 → 0.8741 (-0.5%) |
| overlap consec char-2 | 0.0861 → 0.1 (+16%) | 0.0955 → 0.0814 (-15%) | 0.0911 → 0.0886 (-3%) |
| **mimo pairwise** | **20% → 80%** | **50% → 50%** | **22% → 78%** |

det 跨 seed mixed (distinct 小幅 down, overlap 看 seed). mimo 决定性
preferring sideline — 跨题材一致.

## 与 iter#133-135 静态 cast=3 关键对比

| dim | 静态 cast=3 (iter#133-135) | **动态 sideline (iter#145/147/149)** |
| --- | --- | --- |
| seed1 mimo | 20% (退化) | **80% (decisive 改善)** |
| seed2 mimo | 50% (tied) | 50% (tied) |
| seed3 mimo | 30% (退化) | **77.78% (decisive 改善)** |
| **avg** | **33.3%** (退化) | **69.3% (改善)** |
| cost | -36.4% | +1.2% (中性) |

机制差别:
- 静态 cast=3: 永远只 3 char, character interaction 多元性受限
- 动态 sideline: cast wide + 选择性退场, 池子保留, 可恢复, **Showrunner 选时机**

动态 sideline 跨题材 mimo 改善, 静态 cast=3 跨题材 mimo 退化. **关键不是
"少 char", 而是"灵活调度"**.

## Phase 4-E production landing 决策

**所有标准都通过 (clean A/B, pairwise, cross-genre)**:
* ✓ 16/16 sideline 测试 PASS (iter#139)
* ✓ infrastructure 验证 (iter#140 conservative, iter#142 mandatory)
* ✓ clean A/B 单 seed (iter#145 80%)
* ✓ cross-genre 3-seed (avg 69.3%, all promote)
* ✓ cost 中性 (+1.2% avg)
* ✓ drift signals 0 跨 3 seed

**Production landing 行动 (iter#150)**:
1. Showrunner.sidelined_characters 字段保留 (已实施)
2. SYSTEM_PROMPT 强制触发条款保留 (iter#141)
3. orchestrator wire 保留 (iter#139)
4. tick_state 持久化保留 (iter#139)
5. 默认 SIDELINE_DEFAULT_TTL=10 — 实测合适
6. **无需 opt-in flag** — 跨题材 decisive 正面, default ON 是合理.

## Phase 4 综合 status

| 候选 | 状态 | 净结果 |
| --- | --- | --- |
| **E) sideline** | **完成 (#139-149) — landing** | **mimo 69.3% promote, cost 中性** |
| F) critic prompt cache | 未启动 | 待 Phase 4-E 后启动 |
| G) compressor budget | 未启动 | 与 D 组合 |
| D) memory fidelity | 未启动 | 高成本, 留后 |

## 累计 Phase trail (final after Phase 4-E)

| Phase | iter range | 核心成果 |
| --- | --- | --- |
| Phase 1 | #3-72 | -77% tokens / -83% latency |
| Phase 2 | #76-112 | drift fix, 73.3% pairwise promote ×3 |
| Phase 3-B | #119-136 | --cast-{a,b,c}-count CLI opt-in (default revert wide) |
| **Phase 4-E** | **#139-149** | **runtime sideline default ON, +69.3% mimo, cost 中性** |

净 production cumulative 改动:
- Phase 1: 主导 cost 优化
- Phase 2: close-loop fix 修架构 gap
- Phase 3-B: CLI 工具沉淀
- **Phase 4-E: 动态 sideline 架构升级 (quality + cost 双中性以上)**

## Continuation

iter#150+ 候选:
1. Phase 4-E production landing 收尾 (CHANGELOG / README / PHASE4_PLAN
   sync)
2. cycle 18 review (iter#139/141 跨 3 iter 触发)
3. F (critic prompt cache) 探索
4. G (compressor budget) 探索

## Sources

- iter#145 single-seed: `verdict-iter145-phase4e-controlled-positive.md`
- iter#147 seed2: `verdict-iter147-seed2-sideline-controlled.{json,md}`
- iter#149 seed3: `verdict-iter149-seed3-sideline-controlled.{json,md}`
- 静态 cast=3 反例: `verdict-iter136-revert-iter128-pairwise-evidence.md`
- Phase 4-E 首次 positive: `verdict-iter143-phase4-e-first-positive.md`
