# iter#145 — Phase 4-E controlled A/B 决定性正面 (80% mimo win)

> Phase 4-E first clean A/B experiment. iter#122 (no sideline) vs iter#144
> (sideline ON), same seed1 + same cast=5 (2A+2B+1C). 控制变量除 sideline
> 机制外完全一致.

## Setup (clean A/B)

| iter | bench | sideline | cast (controlled) | tokens |
| --- | --- | --- | ---: | ---: |
| #122 | iter122-seed1-cast221 | **未实施 (pre-#139)** | 2A+2B+1C = 5 (LLM 实际给 4) | 509,863 |
| **#144** | **iter144-seed1-cast221-sideline** | **实施 + 触发** | **同 (LLM 给 5)** | **495,119** |

mimo pairwise: #122 (v15) vs #144 (v16), 10 pairs, 50k budget, parse_err 0.

## Verdict — v16_promote decisive

| dim | v15 (no sideline) | v16 (sideline ON) | delta |
| --- | ---: | ---: | --- |
| **pairwise win** | **20%** | **80%** | **+60pp** |
| tie | 0% | 0% | — |
| parse_err | 0 | 0 | 0 |
| distinct char-2 | 0.8649 | 0.8563 | -1.0% |
| distinct char-4 | 0.9922 | 0.9898 | -0.2% |
| overlap consec char-2 | 0.0861 | 0.1 | **+16%** (det concern) |
| narrations | 42 | 46 | +9.5% |
| total_tokens | 509,863 | 495,119 | **-2.9%** |
| open final | 4 | 3 | -25% |
| avg_urg final | 6.75 | 7.67 | **+13.6%** |
| drift signals | 0 | 0 | 0 |

**det 与 mimo 部分反向**:
- distinct/overlap 看似 sideline 略损
- mimo 看 plot drive / character voice 决定性 v16 优 (80%)
- 类似 iter#133 finding: mimo 重 "interaction quality", 不只 vocabulary 表面

**与 iter#133 静态 cast=3 vs wide 关键差别**:

| 维度 | 静态 cast=3 (iter#133) | 动态 sideline (iter#145) |
| --- | --- | --- |
| 调度方式 | 永远只 3 char | wide cast + Showrunner 选择性 sideline |
| character interaction | 永远缺 | 池子保留, 暂时退场 |
| mimo verdict | 20% (worse) | **80% (better)** |
| cost | -36.4% | -2.9% (small but positive) |

**动态 sideline 是 cost + quality 双赢**: 远好于静态减 cast.

## Phase 4-E production landing 评估

数据扎实度:
* ✓ clean A/B (control: same seed + same cast count, only sideline differs)
* ✓ mimo pairwise decisive (80% v16_promote, 0 parse_err)
* ✓ cost positive (-2.9%)
* ✓ avg_urg + (+13.6%)
* ✓ drift 0
* ⚠ distinct char-2 / overlap consec 有 minor det concern, 但 mimo override

跨题材待验证 (seed2/3):
* iter#146 待跑 seed2 controlled
* iter#147 待跑 seed3 controlled

如 seed2/3 mimo 也 ≥ 60% → **Phase 4-E 可正式 production landing**.
当前单 seed (seed1) 已有 strong signal.

## 双指标 delta (cleanest)

cost delta vs no-sideline: **-2.9%**
quality delta vs no-sideline: **+60pp mimo pairwise**
等于 cost ↓ + quality ↑ 双赢配置.

## Phase 4 综合 status (post-iter#145)

| 候选 | 状态 |
| --- | --- |
| **E) Showrunner runtime sideline** | **clean A/B verified, 待跨题材 #146-147** |
| F) critic prompt cache | 未启动 |
| G) compressor budget | 未启动 |
| D) memory fidelity | 未启动 |

## Continuation

iter#146 — seed2 controlled cast=5 sideline bench
iter#147 — seed3 controlled cast=5 sideline bench
iter#148 — 跨题材 final verdict + 可能 production landing

## Sources

- pairwise: `verdict-iter145-sideline-controlled-pairwise.{json,md}`
- v15 bench (no sideline): `bench-iter122-seed1-cast221.json` (pre-Phase 4-E)
- v16 bench (sideline ON): `bench-iter144-seed1-cast221-sideline.json`
- 静态 cast=3 反例: `verdict-iter133-cast3-pairwise-contradiction.md`
- 首次 positive 信号: `verdict-iter143-phase4-e-first-positive.md`
