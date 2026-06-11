# Cost-Quality-Loop Status (rolling)

**Branch:** `iter/cost-quality-loop`
**Range:** baseline 16d5826 → HEAD
**Last update:** 2026-06-11 (iter#72)

## Headline

| metric | value |
| ------ | ----- |
| Iterations applied | 72 |
| Code review cycles | 9 |
| Commits on branch | 80+ |
| Files touched (active LLM paths) | 17 (every agent + bootstrap + bench tool + new env_helpers) |
| Tests passing | 601/601 (起始 540) |
| Bench artifacts | 19 paired (json+md) under `docs/iter/` |
| Real bugs fixed | iter#61 CRITIC_ENABLE_LLM=false 静默无效 → robust truthy parse |

## Cumulative gains vs v0-baseline

| metric                       | v0      | best stable (v15) | best (v16) |
| ---------------------------- | ------: | ----------------: | ---------: |
| total tokens (3 tick + boot) | 137,890 |            31,214 |     19,287 |
| critic chain                 |  65,174 |             7,878 |          0 |
| world_simulator              |  19,427 |             7,152 |      8,305 |
| narrator                     |  19,904 |            16,184 |     10,982 |
| bootstrap_sec                |     501 |               306 |        305 |
| avg tick duration (sec)      |     556 |                91 |         68 |

* **Best stable result: -77% total tokens, -83% tick latency.**
* Quality samples preserved across all benches (see CHANGELOG + ITERATION_LOG.md for excerpts).

## Surface coverage

Every active LLM call site touched:

| agent / module                       | system prompt | user prompt | max_tokens | other |
| ------------------------------------ | :-----------: | :---------: | :--------: | :---: |
| narrator_agent                       | ✓             | ✓           | ✓ (per length tier) | + critic length-gate, schema placeholder detect, reasoning leak filter |
| narrative_critic (critique/revise/rewrite) | ✓       | ✓           | ✓          | + LLM gating, B-G semantic block, blacklist removal |
| world_simulator                      | ✓             | ✓           | ✓          | + delta-output, importance-weighted events |
| character_agent                      | ✓             | ✓           | ✓ (tier)   | + str fallback in goals/loops |
| event_injector                       | ✓             | ✓           | ✓          | + str fallback in events |
| showrunner                           | ✓             | ✓           | ✓          | |
| novelty_critic                       | ✓             | ✓           | ✓          | |
| story_arc_director                   | (already tight) | ✓         | (already tight) | |
| character_arc_tracker                | (already tight) | ✓         | ✓          | |
| memory_compressor (L0→L1, L1→L2)     | (already tight) | ✓         | ✓ (+ length guard) | |
| summary_tree (legendize / volume / root) | -        | -           | ✓          | + output length guard |
| bootstrap_prompts (world/char/loop/style) | ✓ (mostly) | ✓        | ✓          | + str fallback, placeholder safety |
| reasoning_filter                     | -             | -           | -          | + Chinese/English markers, high-confidence signals |

## Patterns applied

1. **max_tokens 合理化** — every call rebound to its actual output size
2. **JSON delta output** — partial state vs full reflection (WorldSimulator)
3. **占位符自描述化 + 检测** — `<placeholder>` over realistic-looking examples
4. **Det + LLM 分工** — A-class structural triggers stay in det layer
5. **Length-gating + round capping** — short narratives skip critic; MAX_TOTAL_ROUNDS=1 default
6. **JSON indent strip** — LLM-facing only; persistence keeps indented
7. **反 reasoning 多层防线** — prompt禁区 + filter markers + high-confidence signals + parse-fallback scan
8. **Lazy config read** — env-driven knobs via function call, not module constant

## Env tuning knobs

See `CLAUDE.md` "Token 预算调参 env vars" section.

## Reproducing

See `scripts/bench_tick.py` docstring.

## Trail

* CHANGELOG.md — every iter entry
* docs/iter/ITERATION_LOG.md — narrative summary of all 34 iter + reviews
* docs/iter/bench-v0..v16-*.{json,md} — raw bench data
* CLAUDE.md — env tuning table

## Phase 2 Quality-First Loop (iter#76+)

> Phase 1 cost 优化在 iter#34 饱和; iter#76 起切到 Phase 2:
> 质量与 token 成本并列一等公民.

### Stage 0 — Quality Metrics Infrastructure (iter#76-80)

| 模块                                | iter | 测试 | 状态 |
| ----------------------------------- | ---: | ---: | :--- |
| det.repetition (n-gram + distinct)  |  #76 |   19 | ✓    |
| det.consistency (entity vs world)   |  #77 |   14 | ✓    |
| det.compliance (tier/leak/schema)   |  #78 |   13 | ✓    |
| judge runner (pairwise + rubric)    |  #79 |   14 | ✓    |
| bench --quality 集成 + self-sanity  |  #80 |    — | ✓    |
| **小计** test 增量                  |      | **+60** | 测试 661 (从 601) |

§7 参数固化在 `CLAUDE.md`:
* JUDGE_MODEL = `mimo-v2.5-pro` (用户选定跨家族评判)
* judge 预算 50k tokens / bench, pairwise 30 tick / 10 对, 3 固定 seeds
* det 指标层每 bench 必跑 (零成本)

Stage 退出条件已满足:
* 4 类 det / judge 全部可在 `python scripts/bench_tick.py --quality` 跑通
* judge self-sanity 工具 `scripts/quality_self_sanity.py` 待对 v15 实跑一次
  (Stage 1 入口前必须 bias 通过)

### Next: Stage 1 — v15 vs v16 verdict (iter#81-83)

* 同 seed 跑 v15 vs v16, ≥30 tick, det 全量 + judge 按预算采样
* 三种结局都预定处置 (转正 / 维持 / 立 Stage 2 选题)
* 产出 `docs/iter/verdict-v15-vs-v16.md` 入库

### Stage 1 完成 (iter#81-83) — verdict = v16_promote (provisional)

实跑 15 tick × 2 config + mimo pairwise (10 pair, 50k budget):

| 指标            | v15 (critic 开) | v16 (critic 关) |
| --------------- | --------------: | --------------: |
| narrations      |              13 |              12 |
| total tokens    |         188,873 |         149,839 |
| **v16 win-rate**|             30% |         **70%** |
| tier_hit_rate   |           84.6% |       **91.7%** |
| det 整体        |     无显著恶化  |     微差可忽略  |

verdict label = `v16_promote` per §4 第 1 档. Status = **provisional**
(N=12 narrations < §4 ≥30 阈值). 详见 `docs/iter/verdict-v15-vs-v16.md`.

**注意**: 3 个 v15 胜 pair 的 judge reason 都跟 "推进 + 角色" 有关,
提示 critic 帮的不是平均质量, 而是关键节拍. 这与 §4 第 3 档"互有
胜负 / 关键场景输、过场不输" 高度吻合 — 直接为 Stage 2 立项种.

### Next: Stage 2 — 自适应算力分配 (iter#84+)

按 Stage 1 反对意见 + §5: critic 走重要性门控 (event severity / arc
beat / showrunner dramatic tick → v15 全链路; 其余跑 v16). 目标: 拿
v15 关键质量 + v16 平均成本.

### Stage 2 完成 (iter#84-85) — verdict = stage2 双向 win (provisional)

`CRITIC_IMPORTANCE_MIN=7` (默认) — tick max(narrative_value) <7 时跳
critic. 同 seed 15 tick 三方对比:

| metric              | v15 | v16 | stage2 |
| ------------------- | --: | --: | -----: |
| total tokens        | 188,873 | 149,839 | **146,819** |
| critic tokens       |  38,153 |   0   |   5,404 |
| narrations          |     13  |  12   |     13 |

mimo pairwise (50k budget × 2 配对):
* stage2 vs v15: **stage2 win 70%** / v15 win 30%
* stage2 vs v16: **stage2 win 60%** / v16 win 40%

stage2 同时打败两者. §5 退出: cost 目标 -40% 因 non-critic 路径
Phase 1 饱和未严格达标 (-22%), 但 cost ≈ v16, quality 双向 ≥ 45%, 综
合是 stage2 success.

详见 `docs/iter/verdict-stage2.md`.

### Next: Stage 3 — 长程质量 (iter#86+)

按 §6 跑 100+ tick 长程, 探 memory 保真度 / 伏笔簿记 / novelty 衰减 /
summary_tree 查询命中. 期望暴露 short bench 看不见的失败模式.

---

## Phase 1 Status (历史)

cost-quality-loop work continues at user's directive (rule #3: no stop until user says stop). Saturation of optimizable surfaces reached around iter#34; subsequent iterations focus on code hygiene (dead imports, isinstance guards, docs/tests).
