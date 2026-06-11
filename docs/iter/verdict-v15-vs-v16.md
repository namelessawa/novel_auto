# Stage 1 Verdict — v15 vs v16 (canonical)

> **Status:** provisional (本轮 N=12 narrations/config, §4 严格要求 ≥30
> 才转 final). 数据 + 处置定型, 跑足 30 tick 后只需重确认.

## Headline

| metric | v15 (CRITIC_ENABLE_LLM=1) | v16 (CRITIC_ENABLE_LLM=0) |
| ------ | ------------------------: | ------------------------: |
| narrations produced | 13 (out of 15 ticks) | 12 (out of 15 ticks) |
| total tokens (15-tick bench) | **188,873** | **149,839** (-21%) |
| call_count | 46 | 35 |
| narrative chars total | 8,826 | 10,284 |
| tokens / char | 21.4 | 14.6 (-32% per-char) |
| det: distinct char-2 (mean per narration) | 0.894 | 0.862 |
| det: distinct char-4 (mean per narration) | 0.996 | 0.995 |
| det: overlap consecutive char-2 | 0.087 | 0.112 |
| det: tier_hit_rate | 0.846 | **0.917** |

## Judge — pairwise (mimo-v2.5-pro, pairwise_v2 prompt)

- 12 pair candidates, 10 judged (budget 50k tokens)
- **v16 win-rate: 70%** (7 wins)
- v15 win-rate: 30% (3 wins)
- ties: 0, parse errors: 0
- self-sanity (iter#81): bias_score = 0.0 (judge passed)

Sample reasons (judge 给的):

| pair | winner | swap | reason |
| ---- | ------ | ---- | ------ |
| 0 | v15 | True | 段B情节推进更紧凑, 角色反应更生动 |
| 1 | v15 | False | 情节推进明确, 角色决策驱动强 |
| 2 | v16 | True | 情节连贯, 角色细腻, 推进有力 |
| 3 | v16 | True | 环境压迫感强, 角色内心突出, 情节紧张 |
| 4 | v16 | True | 情节推进更清晰, 环境连贯性更强 |

## §4 处置决断

```
v16 win-rate 70% ≥ 45% AND
det 无显著恶化 (overlap +0.025 微升 / distinct char-2 -0.03 微降,
              tier_hit_rate +0.07 反而上升; char-4 distinct 几乎等同)
→ §4 第 1 档: v16 转正候选
```

**Action:** v16 (critic 关闭, 信任 narrator 自身风格纪律) 提升为 best
stable 候选. 当前 provisional 等级由 N 决定: 跑到 ≥30 narration/config
即升级为 final.

## 反对意见 (留作 Stage 2 立项种子)

虽然 v16 平均 win, **3 个 v15-胜 pair 的 judge 理由都跟 "推进 + 角色"
有关** — 提示 v15 critic-loop 帮助的不是 prose-quality 平均, 而是关键
节拍 (cold reading 这 10 个 pair 看不出哪 3 个是"关键节拍"; 长跑 + arc/
severity 标注后才能区分). 这与 §4 第 3 档定义 "互有胜负 / 关键场景输、
过场不输" 高度吻合.

**Stage 2 立项依据:** critic 应改成**重要性门控** (event severity / arc
beat / showrunner-marked dramatic tick → critic 全链路; 其余跑 v16 路径).
预期可拿到 v15 的关键质量 + v16 的平均成本.

## Provisional caveats (跑到 N≥30 前不能视作 final)

1. 12 pair 信号统计意义不强 — 70% 可信区间约 ±25pp (Wilson 95%).
2. 单 seed — §7 默认 3 seed, 当前 1 seed 不能排除题材 sensitivity.
3. v15 critic 在 15 tick 内不一定有触发高 severity 节拍的机会 — 拉长
   tick 数才能暴露 critic 真正护栏价值.
4. det 中 v15 distinct char-2 略高 (-0.03) 但样本小, 噪声范围内.

## Sources

- bench v15: `docs/iter/bench-stage1-v15-15tick.json`
- bench v16: `docs/iter/bench-stage1-v16-15tick.json`
- raw verdict: `docs/iter/verdict-v15-vs-v16-15tick.{json,md}`
- judge self-sanity: `docs/iter/judge-self-sanity-v15-stage0.{json,md}`
- iter trail: iter#82 (runner + v2 prompt), iter#83 (实跑 + 本报告)

## Sample narrative excerpts (Phase 2 §4 mandate)

### v15 sample (tick early)

> 雨水砸下来。每滴带铁锈味, 砸进泥里, 炸开浑浊点... (引自 bench-v15)

### v16 sample (tick early)

> 蒸汽管道又闷响了一声, 铁锈和冷凝水的气味更浓了... (引自 bench-v16)

两段都是高水准的氛围+具象+人物动作开场, 难以人眼区分胜负 — judge 整体倾向
v16 是从"推进感"维度做的判别, 非"写得好不好".
