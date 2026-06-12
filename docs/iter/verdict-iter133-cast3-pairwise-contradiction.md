# iter#133 — cast=3 default 反向: pairwise 80% LOSS vs close-fix wide

> Phase 3-B 真实 quality 验证. mimo pairwise judge 给出与 det 指标**完全相
> 反**的结论. iter#128 default 改 (cast=3) 可能基于错误前提.

## Setup

| iter | bench | config | narrations |
| --- | --- | --- | ---: |
| #105 | iter103-seed1-50tick | close-fix wide (cast ~1) | 44 |
| #126 | iter126-seed1-cast120 | cast=3 (1A+2B+0C) | 42 |

mimo pairwise judge (跨家族 self-bias 最低), 10 pairs, 50k budget.

## Result

**verdict: v15_hold (v16 win-rate 20%, < 35% threshold)**

| dim | close-fix wide | cast=3 | judge says |
| --- | ---: | ---: | --- |
| pairwise win | **80%** | 20% | **wide 完胜** |
| tie | 0% | — | — |

## Det vs pairwise 矛盾

| metric | close-fix wide (v15) | cast=3 (v16) | det 说 | mimo 说 |
| --- | ---: | ---: | --- | --- |
| total_tokens | 544,467 | 483,617 | cast=3 -11.2% (better) | — |
| distinct char-2 | 0.8689 | 0.8913 | cast=3 better (+2.6%) | — |
| distinct char-4 | 0.9916 | 0.9944 | cast=3 better | — |
| overlap consec char-2 | 0.0843 | 0.0908 | wide better (-7.7%) | — |
| tier_hit_rate | 0.75 | 0.7381 | wide better (+1.6%) | — |
| **pairwise prose** | **80%** | **20%** | — | **wide 完胜** |

**det**: cast=3 vocabulary 更多样, prose 更干净, cost 更省.
**mimo**: close-fix wide 显著 (4x 倍率) 更好.

## 解读 — 为什么 mimo 选 wide?

pair samples (5 个):
- pair#0: "情节推进紧凑，角色声音更主动" (wide wins)
- pair#1: "角色声音突出，情节推进连贯" (wide wins)
- pair#2: "A段情节推进更流畅，角色互动增强连贯性" (wide wins)
- pair#3: "对话推进情节高效，角色互动鲜明" (wide wins)
- pair#4: "情节推进更快，角色对话更生动" (wide wins)

mimo 强调 **plot drive + character voice + interpersonal interaction**.
wide (3-4 chars random) 创造更多 interpersonal dynamics; cast=3 (1A+2B+0C
= 1 主角 + 2 配角, 无 NPC) 限制 character interaction 多元.

cast=3 prose **vocabulary** 更多样, 但**叙事 dynamics** 更单调.

mimo 的 prose 评判**重 interaction**, 不太看 vocabulary diversity.

## 跨 Phase 矛盾对比

| comparison | det 结论 | mimo 结论 | 哪个对? |
| --- | --- | --- | --- |
| Phase 2 close-fix vs Phase 2 baseline (#109 #111 #112) | close-fix slight better | **close-fix wins 70-80%** | 一致 — close-fix 真好 |
| **Phase 3-B cast=3 vs close-fix wide (iter#133)** | **cast=3 better** | **wide wins 80%** | **矛盾** |

Phase 2 时 det 与 mimo 一致, Phase 3-B 时 det 与 mimo 反向. 说明 Phase 3-B
det 指标**没有 catch 真正的 prose quality 退化**.

## iter#128 default change reconsideration

iter#128 把 default 从 wide 改成 cast=3 基于:
1. ✓ det cost -8.3% avg (跨 3-seed)
2. ✓ det distinct char-2 +1-3%
3. ✓ det drift 0/0/0 跨 3-seed
4. ❌ **mimo pairwise: 80% LOSS**

如果 quality 是 #1 优先 → 应**回退 iter#128 default 到 wide**.
如果 cost 是 #1 优先 → 接受 cast=3 quality 退化作为 -36.4% cost trade-off.

用户 goal #1 "minimize LLM token cost" 表面像 cost-first. 但 goal #2 "尝试
尽可能多的方向, ... 自我验证小说生成的效果" — 看 mimo 反向, "效果"维度
明确退化.

## 候选 action

iter#134+ 决策树:
1. **REVERT** iter#128 default 回 wide (cost up, quality 维持)
2. **HYBRID**: 添加 `--cast-mode={wide|tight}` flag, 默认 wide (保 quality), tight 是 explicit opt-in (cost-first)
3. **EXPAND** sample: 跑 seed2 + seed3 pairwise 验证 cast=3 在所有题材都败, 还是 seed1 特殊
4. **REDESIGN**: cast=3 + 别的补偿 (e.g. cast=4 with explicit 2A+2B+0C?)

最 conservative + honest: 候选 3 (扩样本到 seed2/3 看一致性), 然后基于
3-seed 完整 pairwise 决定 reverse / hybrid.

## 双指标 delta

cost delta: 无变 (iter#128 仍在效)
quality delta: **-60 pp pairwise win-rate** (close-fix wide 80% vs cast=3 20%)

**这是 Phase 3-B 后续最重要的发现** — det 指标可能 mislead 配置决策.

## Sources

- pairwise: `docs/iter/verdict-iter133-seed1-cast3-vs-closefix.{json,md}`
- v15 bench (close-fix wide): `bench-iter103-seed1-50tick.json`
- v16 bench (cast=3): `bench-iter126-seed1-cast120.json`
- baseline pattern: `verdict-iter112-phase2-close-fix-final.md` (det + mimo 一致案例)
