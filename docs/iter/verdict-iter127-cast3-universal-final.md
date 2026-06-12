# iter#127 — cast=3 universal sweet spot 最终验证 ✓

> verdict-iter126 §Continuation P0: seed3 (plot-dense) with cast=3 验证.
> 结果: cast=3 在 seed3 几乎与 cast=5 平局, narrative tension 反而更好.
> Phase 3-B 最终自适应: **cast=3 universal default**.

## seed3 全 4 config 对比

| iter | seed3 config | actual chars | tokens | distinct char-2 | open | closed | avg_urg |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| #102 | baseline (wide) | 3 (random 离群) | 1,305,466 | 0.8545 | 11 | 0 | 6.09 |
| #104 | close-fix (wide) | 2 | 611,600 | 0.868 | 5 | 1 | 6.80 |
| #121 | cast=5 (2A+2B+1C) | 5 | 496,972 | 0.8787 | 6 | 4 | 7.0 |
| **#127** | **cast=3 (1A+2B+0C)** | **3** | **502,482** | **0.8707** | **4** | **4** | **7.5** |

## #127 cast=3 vs #121 cast=5 (同 seed3, 只换 cast count)

| metric | #121 cast=5 | **#127 cast=3** | delta |
| --- | ---: | ---: | ---: |
| total_tokens | 496,972 | 502,482 | +1.1% |
| narrations | 45 | 40 | -11% |
| distinct char-2 | 0.8787 | 0.8707 | -0.9% |
| open final | 6 | 4 | -33% |
| closed_total | 4 | 4 | 0 |
| **avg_urg final** | **7.0** | **7.5** | **+7.1%** |
| drift | 0 | 0 | 同 |

**几乎平局**: cost +1.1% (噪声), distinct -0.9% (噪声), 但 avg_urg +7.1%
narrative tension 反而更好. open final -33% (池子更干净).

## 3-seed × cast count matrix FINAL

| seed | cast=3 tokens | cast=5 tokens | optimal | margin |
| --- | ---: | ---: | --- | --- |
| seed1 (plot-light) | **483,617** | 509,863 | **cast=3** | **-5.1%** |
| seed2 (plot-medium) | **484,134** | 533,808 | **cast=3** | **-9.3%** |
| seed3 (plot-dense) | 502,482 | 496,972 | cast=5 边际 | +1.1% |
| **avg** | **490,078** | 513,548 | — | **-4.6% avg** |

cast=3 跨 3-seed 平均 cost: **490,078 tokens** (vs cast=5: 513,548).
cast=3 universally wins by **-4.6% avg** vs cast=5.

## Phase 3-B 最终 verdict — cast=3 universal default

* cast=3 ≈ "1 个 A 主角候选 + 2 个 B 重要配角 + 0 个 C NPC".
* 这个配置:
  - plot-light 题材: 防止 wide random 偶发 1 char 过疏 (seed1 wide random 经常给 1-2)
  - plot-medium 题材: 已经接近自然甜点, cast=3 顺势
  - plot-dense 题材: 紧凑而不溢, 与 cast=5 边际差异, urg 反而更高
* 跨 3-seed avg cost **-4.6% vs cast=5, -8.3% vs close-fix wide**

**Production default: `--cast-a-count 1 --cast-b-count 2 --cast-c-count 0`**

## Phase 3 综合 status (Final)

| 候选 | 状态 | verdict |
| --- | --- | --- |
| A) narrator slim | 失败 revert (#114-115) | 教训记录, prose_tail ≠ summaries |
| **B) cast-confound** | **大胜 完整 (#119-127)** | **cast=3 universal -8.3% vs close-fix wide** |
| C) prose diversity dim | 基建完成 (#116-118) | mattr 弱信号但可补 overlap_consec |
| D) memory fidelity | 未启动 | 高成本 200-tick bench |

Phase 3-B 完整 closure, 数据扎实 (4 题材 × 3 cast 模式 = 12 bench).

## 累计 Phase trail

| Phase | iter range | 核心 |
| --- | --- | --- |
| Phase 1 (cost) | #3-72 | -77% tokens / -83% latency |
| Phase 2 (quality close-fix) | #76-112 | drift 1→0, 73.3% pairwise promote ×3, closed=0 leakage 修 |
| **Phase 3-B (cast-confound)** | **#119-127** | **cast=3 universal -8.3% additional cost** |

## Continuation

iter#128+ 候选:
1. (P0) 把 `--cast-a-count 1 --cast-b-count 2 --cast-c-count 0` set 为 cast 默认值 → 改 bootstrap_prompts.py 默认行为
2. (P1) showrunner runtime active-cast 动态 cap (高级特性)
3. (P2) Phase 3-D memory fidelity probe 200-tick bench

## Sources

- bench: `docs/iter/bench-iter127-seed3-cast120.{json,md}`
- analysis: `docs/iter/longrange-iter127-seed3-cast120.{json,md}`
- prior: `verdict-iter121` (seed3 cast=5), `verdict-iter124` (cast=5 mixed),
  `verdict-iter125` (seed2 cast=3), `verdict-iter126` (seed1 cast=3)
