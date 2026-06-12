# iter#124 — Phase 3-B cast-control 3-seed final matrix (nuanced)

> Phase 3-B (iter#119 CLI + iter#121/#122/#124 实战) 3-seed × cast-control
> 完整 matrix. 结果 mixed — 跨题材 NOT 全胜.

## 3-seed × cast-control vs close-fix-wide final matrix

| seed | 题材 | tokens vs close-fix | distinct char-2 | drift | verdict |
| --- | --- | ---: | --- | --- | --- |
| seed3 (末世废土 plot-dense) | iter#104 → #121 | **-19%** | 0.868 → 0.8787 **(+1.6%)** | 0→0 | **大胜** |
| seed1 (蒸汽朋克 plot-light) | iter#105 → #122 | **-6.4%** | 0.8689 → 0.8649 (-0.5%) | 0→0 | **小胜** |
| **seed2** (民国 plot-medium) | iter#107 → #124 | **+1.1%** | 0.8974 → 0.874 **(-3.8%)** | 0→0 | **slight regress** |
| avg | — | **-8.1%** | -0.9% | 0 | **mixed** |

## 解读 — 为什么 seed2 不胜?

seed2 (民国上海) 是 plot-medium 题材, 在 iter#107 close-fix wide 已经处于
"自然甜点" — distinct 0.8974 是 3 seed 最高, tokens 527k 较 seed1/3 适中.

cast control 把 LLM 自由 cast (一般 2) 强制 → 5 (2A+2B+1C). 对于 seed2
这种已经平衡的题材, 多 cast 反而:
- distinct 退 -3.8% (cast 增加, narrator 需轮转, vocabulary 摊薄)
- tokens 微涨 +1.1% (无 net cost gain)
- closed +2 (close 机制更活跃, 但与 cost 节省脱节)

vs:
- seed3 plot-dense 题材: cast random 偶发 3 chars 太密, 5 chars 反而疏松, 净赢
- seed1 plot-light 题材: 1-2 chars 太少, 5 chars 让事件 dispersal 更均衡

**结论**: Phase 3-B cast=5 是题材中等密度 (~3 char wide 默认值附近) 的最佳
设定. 对**偏离默认**的题材 (太疏 seed1 / 太密 seed3) 帮助大. 对**已经接近
默认**的题材 (seed2) 收益甚至负.

## 跨 3 个验证矩阵的 cost evolution

| seed | iter | tokens | mode |
| --- | --- | ---: | --- |
| seed1 | #100 | 521,767 | wide (baseline) |
| seed1 | #105 | 544,467 | wide + close-fix |
| seed1 | **#122** | **509,863** | **cast-5 + close-fix** ✓ |
| seed2 | #101 | 483,857 | wide (baseline) |
| seed2 | #107 | 527,769 | wide + close-fix |
| seed2 | #124 | 533,808 | cast-5 + close-fix ↘ |
| seed3 | #102 | 1,305,466 | wide (baseline) — 离群 |
| seed3 | #104 | 611,600 | wide + close-fix |
| seed3 | **#121** | **496,972** | **cast-5 + close-fix** ✓ |
| **总和** | 7 bench | **5,135,569** | — |
| 平均 / seed | — | ~734k | — |

3-seed cast-5 平均: (509,863 + 533,808 + 496,972) / 3 = **513,548 tokens**

3-seed close-fix wide 平均: (544,467 + 527,769 + 611,600) / 3 = **561,279 tokens**

**Phase 3-B 跨 3-seed 平均 cost: -8.5%**

## Phase 3-B 整体 verdict

* 跨题材**平均 cost -8.5%** vs close-fix wide
* 跨题材**平均 distinct char-2 -0.9%** (噪声层级)
* 跨题材**drift 全部 0** (维持)
* 但题材**敏感**: seed2 微负, seed3 大正, seed1 小正

## 关键发现 — cast=5 不是 universal optimum

Phase 3-B 治理是 **配置点 problem**, 非 universal fix.
"恰好 5 个" 适合中-高 plot density 题材, 不适合所有.

**iter#125+ 候选**:
1. (P0) cast count sweep: cast=3/4/5/6 跨 seed × density 找 optimal
2. (P1) 根据 plot/cast density 动态选 cast count (showrunner runtime cap)
3. (P2) seed2 用 cast=3 或 cast=4 重 bench, 看是否优于 wide

## Phase 3 综合 status update

| 候选 | 状态 |
| --- | --- |
| A) narrator slim | 失败 revert (iter#114-115) |
| **B) cast-confound** | **跨 3-seed 完成, 平均 -8.5% cost, 但 seed-specific (#119-124)** |
| C) prose diversity dim | 基建完成弱信号 (#116-118) |
| D) memory fidelity | 未启动 |

Phase 3-B 部分胜利, 不是 Phase 2 close-fix 那种 universal robust.

## Sources

- bench: `docs/iter/bench-iter124-seed2-cast221.{json,md}`
- analysis: `docs/iter/longrange-iter124-seed2-cast221.{json,md}`
- baseline: `verdict-iter101-stage5-seed2-50tick.md`
- close-fix: `verdict-iter107-3-seed-close-matrix.md` §seed2
- 3-seed Phase 3-B 跨题材: `verdict-iter121-cast-confound-confirmed.md`, `verdict-iter122-cast-seed1.md`
