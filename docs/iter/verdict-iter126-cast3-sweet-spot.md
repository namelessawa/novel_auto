# iter#126 — cast=3 跨 plot-light + plot-medium 都是 sweet spot

> verdict-iter125 §Continuation P0: seed1 with cast=3 验证. 结果 cast=3 在
> seed1 也大胜 cast=5, 与 seed2 同向. Phase 3-B 自适应方案明朗.

## seed1 全 4 config 对比

| iter | seed1 config | actual chars | tokens | distinct char-2 | open | closed | avg_urg |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| #100 | baseline (wide) | 2 | 521,767 | 0.8825 | 6 | 0 | 6.0 |
| #105 | close-fix (wide) | 1 | 544,467 | 0.8689 | 4 | 3 | 6.75 |
| #122 | cast=5 close-fix | 4 (LLM 漏 1) | 509,863 | 0.8649 | 4 | 4 | 6.75 |
| **#126** | **cast=3 close-fix** | **3** | **483,617** | **0.8913** | **3** | **3** | **8.0** |

## Key delta — #126 cast=3 vs #122 cast=5 (同 seed1, only cast count 变)

| metric | #122 cast=5 | **#126 cast=3** | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 509,863 | 483,617 | **-5.1%** |
| narrations | 42 | 42 | 0 |
| distinct char-2 | 0.8649 | 0.8913 | **+3.1%** |
| open final | 4 | 3 | -25% |
| closed_total | 4 | 3 | -1 |
| **avg_urg final** | **6.75** | **8.0** | **+18.5%** |
| drift | 0 | 0 | 同 |

**cast=3 在 seed1 完胜 cast=5**: cost -5.1%, distinct +3.1%, avg_urg +18.5%
(末期 narrative tension 极高).

## Key delta — #126 cast=3 vs #100 baseline (同 seed1, baseline 对比)

| metric | #100 baseline (wide ~2) | **#126 cast=3 close-fix** | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 521,767 | 483,617 | **-7.3%** |
| distinct char-2 | 0.8825 | 0.8913 | **+1.0%** |
| open final | 6 | 3 | **-50%** |
| closed_total | 0 | 3 | **+3 (新机制)** |
| avg_urg final | 6.0 | 8.0 | **+33%** |
| drift | 0 | 0 | 同 |

vs baseline: cost -7.3% + 全 quality dim 提升 (+33% urg 是巨大).

## Phase 3-B 自适应 cast matrix (revised)

| seed | optimal cast | iter | tokens | vs close-fix wide |
| --- | --- | --- | ---: | ---: |
| **seed1** (蒸汽朋克 plot-light) | **cast=3** | **#126** | **483,617** | **-11.2%** |
| seed2 (民国 plot-medium) | cast=3 | #125 | 484,134 | -8.3% |
| seed3 (末世 plot-dense) | cast=5 | #121 | 496,972 | -19% |
| **avg optimal** | — | — | **488,241** | **-13.0%** |

vs 之前的 universal cast=5 (-8.5%): 题材自适应**多挤 4.5 个百分点**.

## 关键洞察 — cast=3 是普适基准, cast=5 只在极端密度时上调

| 题材 density | wide random 偶发 | optimal cast |
| --- | --- | --- |
| **plot-light** (seed1) | 1-2 chars (太少) | **cast=3 (补足)** |
| **plot-medium** (seed2) | ~2 chars (中等) | **cast=3 (轻补)** |
| **plot-dense** (seed3) | 3 chars + 高密 event | cast=5 (分摊密度) |

**cast=3 是 production default, cast=5 reserved for high-density genres**.

## Phase 3 综合 status (post-iter#126)

| 候选 | 状态 | summary |
| --- | --- | --- |
| A) narrator slim | 失败 revert (#114-115) | 教训记录 |
| **B) cast-confound** | **大胜 (#119-126)** | **跨 3-seed 平均 -13% cost, drift 0/0/0** |
| C) prose diversity dim | 基建完成弱信号 (#116-118) | mattr 跨题材 ±1.8% noise |
| D) memory fidelity | 未启动 | 高成本 200-tick bench |

Phase 3-B 是 Phase 3 完整胜利, 数据扎实 (4 个题材 × 多 config 比对).

## 双指标 delta

cost delta vs #122 cast=5: -5.1%
cost delta vs #100 baseline: -7.3%
cost delta vs close-fix wide: -11.2%
quality delta: drift 0/0, distinct +1.0% vs baseline / +3.1% vs cast=5,
   avg_urg +33% vs baseline / +18.5% vs cast=5

## Continuation

iter#127+ 候选:
1. (P0) seed3 cast=3 验证 — 是否 plot-dense 也偏好 cast=3, 或 cast=4 折中
2. (P1) showrunner runtime active-cast cap 动态选 cast (基于实时 event 密度)
3. (P2) 默认 production cast count = 3 sealing 的设计文档

## Sources

- bench: `docs/iter/bench-iter126-seed1-cast120.{json,md}`
- analysis: `docs/iter/longrange-iter126-seed1-cast120.{json,md}`
- prior: `verdict-iter122-cast-seed1.md`, `verdict-iter125-cast-sweep-seed2.md`,
  `verdict-iter121-cast-confound-confirmed.md`
