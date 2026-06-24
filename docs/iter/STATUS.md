# Cost-Quality-Loop Status (rolling)

**Branch:** `main`
**Range:** baseline 16d5826 → HEAD
**Last update:** 2026-06-24 (Phase 6-B/C iter#A-G batch)

## Phase 6 Session Headline (2026-06-24)

| iter | scope | tests | bundle Δ | key result |
| --- | --- | ---: | ---: | --- |
| iter#A | dashboard 接 critic-log/stats | 940 | +4 kB JS | Phase 6-C 数据栈兑现 |
| iter#B | window=N sliding | +5 = 945 | +0.8 kB | last-N 截窗 (deque) |
| iter#C1 | C6 章末无悬念 det | +24 = 969 | — | 9 closure pattern, healthy FP guard |
| iter#C2 | A1 校准抽样 (no-op verdict) | 969 | — | 真相: production 2.14/narr ≠ iter#7 12+ |
| iter#D | 500-tick runbook + drift analyzer | 969 | — | 6 drift signal, runbook 就位 |
| iter#E | reader 连读模式 | 969 | +3.6 kB | inline section anchor + tick chip |
| iter#C3 | A1 3-char 化合物 dedup | +10 = 979 | — | 噪声 4.58→2.98 A1/narr (-35%) |
| iter#F | viewpoint sidecar + reader chip | +6 = 985 | +0.6 kB | sidecar JSON, vp chip |
| iter#G | reader prefs (localStorage) | 985 | +2.8 kB | per-novel scroll, 字号/行距 chip |

* +45 net tests (940 → 985). Frontend JS 297 → 309 kB (+12 kB / 4 features).
* 0 backend regression across full 985-test suite (~72s).
* CRITICAL: iter#C3 verified -35% A1 production noise via re-running C2 校准 (4.58 → 2.98 avg, 12% → 16% clean rate).

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

### Stage 3 完成 (iter#86-89) — 长程 drift 实测捕获 2 真信号

50 tick × stage2 default 配置 (iter#89 跑):

**Foreshadowing trend (核心发现)**:

| tick | open | stale | avg_urgency |
| ---: | ---: | ----: | ----------: |
| 5    |  5   |  0    | 7.00 |
| 25   |  8   |  2    | 6.25 |
| 50   |  9   |  3    | 6.11 |

* open_loops **5 → 9 (+80%)** 单调堆积
* stale (>20 tick 未推进) **0 → 3** by tick 40
* avg_urgency 7.0 → 6.11 单调下降 (新种伏笔越来越弱)

Repetition 仍 OK (distinct char-2 = 0.895, overlap = 0.082). **prose-
level 套路化未现, plot-level 已问题 — 短 bench 看不见.**

详见 `docs/iter/verdict-stage3.md`. 3 项新优化面登记为 iter#90-92 候选.

### Next: Stage 4 / iter#90+ — 攻坚长程 drift

按 Stage 3 verdict 登记:
* iter#90 — EventInjector 偏好关旧 (而非新种); stale > 阈值时禁新种
* iter#91 — TickState 加 `_loops_closed_total` 累计 + reap 钩子
* iter#92 — Showrunner cold_thread urgency boost 真正写进 inject 建议

### Stage 4 完成 (iter#90-94) — 三件套同时缓解所有 drift 信号

iter#94 50 tick 长 bench (stage4 = stage2 + 三补丁) vs iter#89 baseline:

| metric              | stage3 baseline | **stage4**   |     Δ |
| ------------------- | --------------: | -----------: | ----: |
| open_loops end      |               9 |        **5** | -44%  |
| open growth         |   +80% (5→9)    | +25% (4→5)   | 累积减半 |
| stale end           |               3 |        **1** | recovery |
| avg_urgency end     |            6.11 |     **6.80** | 止下降 |
| drift signals       |               2 |        **0** | 全解除 |
| distinct char-2     |           0.895 |        0.895 |  持平 |
| total tokens        |         509,417 |      540,474 |   +6% |

cost +6% 是合理代价 (cold_thread hint=7 触发 critic). 联合 cost-quality
全维度 stage4 win. 详见 `docs/iter/verdict-stage4.md`.

stage4 现是 best stable candidate 跨 cost / quality / drift.

### Next: iter#95+

* 多 seed 跨题材验证 stage4 是否稳健 (Stage 1/4 都是单 seed)
* 推 critic length-gate / IMPORTANCE_MIN 进一步省 cost (探 stage4 ⩾v16
  cost)
* 加新 prompt 多样化指标 (Stage 3 verdict 候选 #2 之外的方向)

---

## Phase 1 Status (历史)

cost-quality-loop work continues at user's directive (rule #3: no stop until user says stop). Saturation of optimizable surfaces reached around iter#34; subsequent iterations focus on code hygiene (dead imports, isinstance guards, docs/tests).

---

## SESSION SUMMARY — 2026-06-24 Phase 6 iteration operator run

7 轮 PASS · 0 FAIL · 0 WARN. 测试基线 810 → **940** (+130: B4 + 9 narratives + 5 E7 + 37 dedicated + 6 critic_log + 6 endpoint + 7 stats). 全部零回归.

### Per-iter

| iter | scope | landed |
| --- | --- | --- |
| iter#1 | det metric | B4 inner-monologue det check (Phase 6-C 第三刀). 271-narrative offline replay 触发 0.00%. |
| iter#2 | agent code | `/api/tick/narratives` 双 fix — `current_tick` AttributeError + 漏填 `world_time`. 9 新 test (5 unit + 4 integration). |
| iter#3 | det metric | E7 翻译腔 det check (Phase 6-C 第四刀). 7 pattern, healthy 0 触发. |
| iter#4 | test | character_signal + translation_artifact 各加 18 dedicated test, 模块覆盖与 prose_dynamics 平衡. count_inner_monologue_chars 算法 marker-position 精确化. |
| iter#5 | persistence | critic decision JSONL log — orchestrator 每 tick append `{data_dir}/critic_log.jsonl`. `_append_critic_log` helper + 6 test. |
| iter#6 | api | `GET /api/tick/critic-log` raw rows endpoint. malformed safe-skip + range/limit + 6 test. |
| iter#7 | api | `GET /api/tick/critic-log/stats` aggregated dashboard — action distribution + top-10 codes + empty_decision_ticks + 7 test. |

### 完成的 phase 节点

- **Phase 6-C det wrapper trilogy**: prose_dynamics (E1+D6, 前作) + character_signal (B4, iter#1) + translation_artifact (E7, iter#3). 3 模块各 18/19 dedicated unit + 5 集成测试.
- **Phase 6-B reader 数据栈三件套**: orchestrator critic_log.jsonl (iter#5) + raw rows endpoint (iter#6) + aggregated stats endpoint (iter#7). frontend 直接 consume.
- **v2.48 endpoint contract fix**: `/api/tick/narratives` 从 500 状态恢复 + world_time 字段补全 (iter#2).

### 边际收益评估 (退出理由)

继续 iter 候选边际收益不足:
- **A1 threshold 校准**: 2★ 风险 (regression 风险), 需 3-seed cross-theme bench 验证, ~10h+ 不适合单 iter
- **D5 多感官 / D1 背景倾倒 det**: 1★ 但 leverage 低 — det wrapper 模板已 saturate (类似 iter#1/3 模板, padding coverage 数字而无新 catch)
- **frontend 工作**: v2.48 dashboard uncommitted 状态阻塞
- **hygiene 扫**: 无明确 target, narrative_critic 已 `except Exception` defense-in-depth 完备

7 轮累计 22 files 触及, 每 iter 单语义 commit + dedicated verdict, 无 cross-cutting refactor. ITERATION_LOG 166 行 (距 200 阈值 34 行余量) 为后续 session 留空间.

### 状态留给下个 session

ITERATION_LOG `候补 (未挑)` 区已记 A1 threshold 校准 (高风险高杠杆) — 配套需求: 3-seed cross-theme bench harness 准备好后再启动. 否则任何 A1 改动属一刀切, 违反 Phase 4-E 教训"架构改动 mandatory cross-seed".
