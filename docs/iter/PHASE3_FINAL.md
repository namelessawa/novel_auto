# Phase 3 Final Verdict (revised iter#136)

> Phase 3 (iter#113-136) 综合 closure: A 失败 / **B opt-in only** / C 弱信号 / D 未启动.
> v2.42 production default = wide range (Phase 2 一致). Phase 3-B CLI 保留作 cost-first opt-in.
>
> **重要 revision**: iter#128 把 default 改 cast=3 基于 det 指标, iter#133/#134/#135
> mimo pairwise 反向 (cast=3 跨 3-seed 33% vs wide 63%). iter#136 REVERT.
> 详见 verdict-iter136-revert-iter128-pairwise-evidence.md.

## Phase 3 iter trail (#113-129)

| iter | type | candidate | status |
| --- | --- | --- | --- |
| #113 | doc | PHASE3_PLAN | A/B/C/D 候选打包 |
| #114 | code | A narrator slim | 实施 |
| #115 | bench+revert | A | **失败 -4.9% / -12.7% urg → revert** |
| #116 | code | C diversity dim | 新模块 TTR/MATTR/句长 |
| #117 | review | C | cycle 15 fix |
| #118 | doc+script | C | 离线 cross-bench, mattr 弱信号 |
| #119 | code | B cast-confound CLI | --cast-{a,b,c}-count |
| #120 | doc | pause | env block status |
| #121 | bench | B (seed3 cast=5) | **-62% vs baseline 大胜** |
| #122 | bench | B (seed1 cast=5) | -6.4% small win |
| #123 | review | B | cycle 16 fix |
| #124 | bench | B (seed2 cast=5) | +1.1% slight regress |
| #125 | bench | B (seed2 cast=3) | -9.3% vs cast=5 |
| #126 | bench | B (seed1 cast=3) | -5.1% vs cast=5 |
| #127 | bench | B (seed3 cast=3) | +1.1% vs cast=5 (平局) |
| #128 | code | B default 落地 | wide → cast=3 (后 revert) |
| #129 | review | B | cycle 17 fix |
| #130 | doc | B | PHASE3_FINAL.md (本文档) |
| #131 | smoke | B | cast=3 default 端到端验证 |
| #132 | doc | B | README cast=3 guide |
| #133 | bench | B (seed1 pairwise) | **cast=3 20% vs wide 80%** v15_hold |
| #134 | bench | B (seed2 pairwise) | cast=3 50% vs wide 50% borderline |
| #135 | bench | B (seed3 pairwise) | cast=3 30% vs wide 60% v15_hold |
| **#136** | **code** | **B REVERT iter#128** | **default 回 wide, cast=3 仍 opt-in** |

20 iter Phase 3-B (含 revert) / 3 iter Phase 3-A / 3 iter Phase 3-C / 0 iter Phase 3-D.

## Phase 3-B FINAL matrix

### 3-seed × cast=3 vs cast=5

| seed | cast=3 tokens | cast=5 tokens | optimal | -% vs cast=5 |
| --- | ---: | ---: | --- | ---: |
| seed1 (蒸汽朋克 plot-light) | **483,617** | 509,863 | cast=3 | **-5.1%** |
| seed2 (民国 plot-medium) | **484,134** | 533,808 | cast=3 | **-9.3%** |
| seed3 (末世 plot-dense) | 502,482 | 496,972 | cast=5 边际 | +1.1% (噪声) |
| avg | **490,078** | 513,548 | cast=3 | **-4.6%** |

### cast=3 vs close-fix wide

| seed | cast=3 | close-fix wide | -% |
| --- | ---: | ---: | ---: |
| seed1 | 483,617 | 544,467 | -11.2% |
| seed2 | 484,134 | 527,769 | -8.3% |
| seed3 | 502,482 | 611,600 | -17.8% |
| avg | 490,078 | 561,279 | **-12.7%** |

### vs Phase 2 baseline (no close-fix, wide cast)

| seed | cast=3 | baseline | -% |
| --- | ---: | ---: | ---: |
| seed1 | 483,617 | 521,767 | -7.3% |
| seed2 | 484,134 | 483,857 | +0.06% (持平) |
| seed3 | 502,482 | 1,305,466 | -61.5% (戏剧) |
| avg | 490,078 | 770,363 | **-36.4%** |

## Quality 维度 — det 看似 OK, mimo pairwise 反向

跨 Phase 3-B 3-seed × cast=3 (**det 视角**):
* drift signals: 0 / 0 / 0 ✓
* distinct char-2: 0.8913 / 0.8886 / 0.8707 (跨 3 seed σ ~1%)
* avg_urg final: 8.0 / 7.33 / 7.5 (跨 3 seed σ ~5%, 均 > 7)
* narrative tension 全部 > Phase 2 baseline

**但 mimo pairwise (iter#133/#134/#135 实测) 反向**:

| seed | cast=3 win | wide win | tie | verdict |
| --- | ---: | ---: | ---: | --- |
| seed1 | 20% | **80%** | 0% | v15_hold |
| seed2 | 50% | 50% | 0% | v16_borderline |
| seed3 | 30% | **60%** | 10% | v15_hold |
| **avg** | **33.3%** | **63.3%** | 3.3% | **wide preferred** |

cast=3 = 1A+2B+0C 无 NPC → character interaction 多元性受限. det 不测
这个维度. mimo 重 plot drive / character voice / interaction.

**Phase 3-B det 单点验证是错误流程**. Phase 2 close-fix 当时跑了 pairwise
验证 (#109/#111/#112), Phase 3-B iter#119-128 漏跑直接改 default.

## iter#136 REVERT verdict

iter#128 cast=3 default 改基于 det 错觉, iter#136 REVERT:
* default 回 wide range
* Phase 3-B CLI (--cast-{a,b,c}-count) 保留作 cost-first opt-in
* Phase 3-B 净 production behavior: 无 default 变化, 但增 opt-in 工具

## 累积 Phase trail (iter#136 revert 后修正)

| Phase | iter range | 核心成果 |
| --- | --- | --- |
| Phase 1 (cost) | #3-72 | -77% tokens / -83% latency |
| Phase 2 (quality close-fix) | #76-112 | drift 1→0, 73.3% pairwise promote ×3 |
| **Phase 3-B (cast-confound)** | **#119-136** | **CLI 保留作 cost-first opt-in, default 不变** |
| **Phase 3 net** | — | **0 default cost change; opt-in -36.4% cost trade-off available** |

### 跨 Phase 累积 cost reduction (revised)

baseline v1.x (Phase 1 起点): assume 100% cost reference
Phase 1 end (iter#72): 23% cost
Phase 2 end (iter#112): ~25% (微涨, close-fix +1-4%)
**Phase 3-B default (iter#136 revert)**: ~25% (与 Phase 2 一致, 默认无变)

**净 -75% vs v1.x baseline** (Phase 1 主导, Phase 2/3 quality 维持).

opt-in cost-first 模式 (--cast-a-count 1 --cast-b-count 2 --cast-c-count 0):
- 可达 ~14.6% of v1.x baseline (≈ -85.4%)
- 代价: mimo pairwise -30pp (quality 退化)
- 适用 cost-critical 生产场景

## Phase 3-A (失败) 教训

iter#114 试 narrator user_prompt summaries [-5:] → [-3:]:
- 预期 -1.5% cost
- 实测 +4.9% cost, avg_urg -12.7%, overlap_consec_4 +226%
- 原因: summaries 与 prose_tail 是不同抽象层 (前情张力锚 vs 续写连贯锚),
  砍 summaries → LLM 失远期 plot 上下文 → 自我重复 → 多轮 critic 补救净涨

**教训**: user_prompt 字段不是字数游戏, 每个字段承载独立功能. 下次
ablation 需先 mock 量化字段边际贡献.

## Phase 3-C (弱信号) 教训

iter#116-118 quality_metrics/diversity.py:
- TTR / MATTR / 句长 stats 新模块
- 跨 7 bench 离线分析: mattr 在 iter#114 反向抓 -1.2%, 但与 close-fix 3-seed
  自然变异 ±1.8% 重叠, 不能 confident 单维区分
- ttr_word 跨 bench 0.7% 范围, 死信号
- 净: 补 overlap_consec 的弱辅助维度

**教训**: 度量层加新 dim 之前应先验证它能 catch 已知 regression. Phase 3-C
的发现是 mattr 跨 seed 稳定但不够敏感.

## Phase 3 production default 改动总览

```
v2.40 → v2.41 (iter#128/129):
* backend/bootstrap_prompts.py:
  - 默认 cast: wide 6-10 (3A+3-4B+2-3C) → 3 (1A+2B+0C)
  - 用户显式 --cast-{a,b,c}-count 仍可覆盖, all-or-nothing
  - 加 cast count compliance check (warning only)
* PROMPT_CHARACTERS:
  - {cast_breakdown} / {cast_tiers} 占位符 (iter#119)
  - 默认 "3 个起始角色 (推荐配置)" (iter#128, iter#129 去 internal taxonomy)
* CLI: --cast-a-count / --cast-b-count / --cast-c-count
```

## Phase 3-D 候选 (未启动)

memory fidelity probe 200-tick bench:
- 单 seed 200 tick ≈ 3-4 hr / ~2M tokens
- 跨 tick 50/100/150/200 抓 L3 传说一致性
- 现 quality_metrics/longrange.py 已有 MemoryProbe + reducer (iter#86)
- 集成到 bench_tick.py 需要 ~1 iter

留作 Phase 4 候选.

## Continuation

iter#130+ 候选 (按优先):
1. (P0) Phase 3 verdict 推广验证 — 新 seed 跑 cast=3 default 看是否仍 robust
2. (P1) cycle 18 review 周期 (iter#130-132 触发)
3. (P2) Phase 3-D memory fidelity probe 集成 (高成本但有价值)
4. (P3) showrunner runtime active-cast 动态 cap (architectural 大改)

## Sources

- All verdicts: docs/iter/verdict-iter1{13-29}*.md
- All benches: docs/iter/bench-{iter114-127,stage5,iter103}*.{json,md}
- 3-seed × cast matrix consolidated 见此文档
- Phase 2 final: verdict-iter112-phase2-close-fix-final.md
- Phase 1 trail: CHANGELOG v2.38 iter#3-72
