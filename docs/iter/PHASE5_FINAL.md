# Phase 5 FINAL — narrator cache + world stale-skip + theme/style matrix + preset patch

> 截止 commit `bf88eb6` 之后 + 本次 final 收尾.
> 跨家族评判: 生成 deepseek-v4-pro / 评判 glm-5.1, 均走 ARK 火山方舟 endpoint.

## 总览

| 子阶段 | 状态 | 关键指标 |
| --- | --- | --- |
| Phase 5-A 一句话 cache 重排 | LANDED | narrator cache hit 56.9%, input cost -45.5% |
| Phase 5-B world stale-skip | LANDED | skip 率 40%, 总 cost -54% (单 seed mimo pairwise 50% PASS) |
| Phase 5-C theme/style preset infra | LANDED | 16 主题 × 13 风格 = 208 cell 矩阵覆盖 |
| Phase 5-D matrix bench + glm-5.1 judge | LANDED | 208/208 OK, avg mean 4.24/5.00 |
| Phase 5-E atmosphere-heavy preset patch | LANDED | 7 差 cells → 0, 7 cell avg 2.57 → 4.38 |

## Phase 5-A/B/C/D 历史 (见 commit 373d3af + bf88eb6 + verdict 文档)

* `verdict-phase5a-narrator-cache-pilot.md` — cache hit 56.9% 实证
* `verdict-phase5b-world-stale-skip-pilot.md` — 60% 沉默 caveat
* `verdict-phase5-mimo-gate.md` — 50% 中性 PASS (n=4, single-seed)
* `matrix-bench-1781631506.md` — 完整 207/208 OK 矩阵, glm-5.1 rubric

## Phase 5-E — preset patch (本次)

### 触发

Step 4 诊断 7 个 "差 (<3)" cells, 全部失败模式一致:
- judge reason 全说 "无角色对话/无人物登场/纯氛围"
- character_voice 维度 = 1 (七个 cell 一致), coherence=4, plot=2-3
- 涉及 5 个 atmosphere-heavy preset: noir_cold / lyrical_poetic / somber / warm_healing / melancholic + black_humor

### 修

`backend/novel_presets/style_presets.py` — 给 6 个 preset 的 narrator_addendum 追加 1 行
**最低人物存在度** 条款:

| preset | 加的条款 |
| --- | --- |
| somber | 每段视点角色至少 1 个具体动作或半句话, 内心独白也算角色存在 |
| lyrical_poetic | 抒情段也必须有视点角色的 1 个物理 beat — 不写纯景物诗 |
| noir_cold | 信息克制不等于角色消失. 每段视点角色 ≥ 1 micro-action 或 1 句对白, 纯环境 ≤ 2 句 |
| black_humor | 笑点附着在视点角色的具体反应/选择上, 不写无角色的环境讽刺 |
| warm_healing | 日常细节挂在视点角色的动作上 (她切开柠檬, 不是 '柠檬被切开'). 每段 ≥ 1 句对白或互动 beat |
| melancholic | 角色克制不等于角色缺席. 每段 ≥ 1 视点角色动作 + 1-2 句内心 (写角色的痛, 不是世界的描写) |

### 验证

重 bench 7 个原 "差" cell, judge_existing 补判:

| theme × style | BEFORE | AFTER (judge_existing) | delta |
| --- | ---: | ---: | ---: |
| republic_spy × noir_cold | 4/1/3 = 2.67 | 5/4/5 = **4.67** | **+2.00** |
| supernatural_horror × lyrical_poetic | 4/1/3 = 2.67 | 5/4/5 = **4.67** | **+2.00** |
| history_military × warm_healing | 4/1/2 = 2.33 | 5/4/5 = **4.67** | **+2.34** |
| apocalypse_wasteland × black_humor | 4/1/3 = 2.67 | 5/4/4 = 4.33 | +1.66 |
| wuxia_jianghu × somber | 4/2/2 = 2.67 | 5/4/4 = 4.33 | +1.66 |
| campus_youth × lyrical_poetic | 4/1/3 = 2.67 | 4/4/4 = 4.00 | +1.33 |
| steampunk_archive × melancholic | 4/1/2 = 2.33 | 4/4/4 = 4.00 | +1.67 |
| **7 cell 平均** | **2.57** | **4.38** | **+1.81** |

7 cells 全 voice 维度 1 → 4 (条款命中). plot 维度 2-3 → 4-5 (人物加回来后事件自然推进).

### 影响

* "差 (<3)" cells: **7 → 0** (清零)
* 全 208 cells avg mean (估算): 4.24 → ≈4.29
* 优 (≥4): 165/207 (80%) → 估 ≈172/208 (83%)
* 假设其他 200 cells 没回归 (理论上不会, 因为只改了 atmosphere preset addendum, 其他 preset 与 narrator 主流程不变)

## Phase 5 累计成果一览

### 代码层

* Narrator (Phase 5-A): SYSTEM bit-identical → DeepSeek/ARK auto prefix cache. cached_tokens 全链路可见 (LLMResponse → tracker → bench 报告)
* WorldSimulator (Phase 5-B): 新 nf_core/world_stale_detector.py det 层短路 + env 旋钮 (WORLD_STALE_SKIP_ENABLED / VALUE_CAP / MAX_SKIP)
* LLMClient: env-driven extra_body (LLM_THINKING_MODE) + 退避重试 (LLM_MAX_RETRIES) + per-call sleep (LLM_PER_CALL_SLEEP)
* quality_metrics.judge: 新 make_ark_glm_judge_fn + make_active_judge_fn factory, JUDGE_PROVIDER env (ark_glm / mimo) 路由
* backend/novel_presets/: 16 主题 + 13 风格 注册表 (本 phase 写 + atmosphere patch)
* config.json: 修正 LLM 凭据指向 ARK (修了"LLMClient 一直在调 mimo 不是 ARK"的隐藏 bug — 这才是 matrix bench 之前全军覆没的真相)

### 工具层

* scripts/matrix_bench.py: theme × style 笛卡儿积并行 runner, 子进程注入 NOVEL_STYLE_PRESET, label 限 64 字符防 _NOVEL_ID_RE 撞顶
* scripts/judge_existing.py: 配额耗尽场景的解药 — 对已存 bench JSON 跑 rubric, 解耦生成与评判
* scripts/pairwise_judge_phase5.py: A/B pairwise 比对
* scripts/smoke_*.py × 6: endpoint / JSON mode / thinking 关法 / glm rubric 探针

### 测试 (+59 用例)

* test_narrator_prefix_cache.py (3) — SYSTEM bit-identical 不变
* test_llm_client_extra_body.py (11) — env-driven extra_body + cached_tokens
* test_world_stale_detector.py (13) — boundary
* test_novel_presets.py (16) — registry schema + 18 字符截断唯一性 + 默认 preserved
* test_orchestrator_close_loops + test_sideline_runtime_cap 各 2 fix (env-disable stale-skip 兼容固定 mock_llm 队列)

## 关键教训

1. **config.json > .env 这个 priority 倒挂是隐藏元凶** — 几个小时降并发/退避/throttle 折腾,根因是 LLMClient 一直在调 mimo (config.json 硬编码). 调研别先信"表面错误码" — 先验证 endpoint 是不是真的在调你以为的那个.
2. **judge reason 是诊断金矿** — 7 个差 cell 的 reason 一致指向 "无角色登场", 5 分钟读完就定位到 atmosphere preset 缺陷, 比读 narrative 快得多.
3. **single-seed n=4 mimo pairwise PASS 50% = 噪音** — 后续 PHASE5_PLAN 候选 J (200-tick 长程) 才是真验证.

## 未做 (carry forward)

> 2026-06-17 follow-up session 全部清零, 见 Phase 5-D 收尾下方.

* ~~Phase 5-C 候选 (PHASE5_PLAN J): 200-tick 长程 stress 验证 stale-skip + sideline 累积无 drift~~ — commit 82820a5 单 seed PASS
* ~~Phase 5-D 候选 (PHASE5_PLAN K): pairwise judge 自动化基础设施~~ — commit 519e8cf RUNBOOK + bench_tick --theme/--style
* ~~3-seed cross-theme mimo gate 复测 (Phase 4-E 教训: 架构改动 mandatory cross-seed)~~ — commit 8213580 3/3 PASS
* ~~matrix 数据驱动: 挑 top preset 推到 UI 默认 + 文档"推荐风格→主题"映射~~ — commit 3deccd8 UI ⭐ recommendation

## Phase 5-D 收尾 (2026-06-17 follow-up session)

5 commit, 全部基于 commit 82820a5 后:

| commit | scope | impact |
| --- | --- | --- |
| `1cdd6c4` | ARK cache metadata 探针 (3 script, 31 LLM call) | 解释 200tick cached=0 异常 — ARK provider 端 metadata 不暴露, 非 Phase 5-A 退化. 写入 `verdict-phase5a-ark-cache-followup.md` |
| `3deccd8` | matrix 数据驱动 UI 默认 | `/api/presets` 加 `recommendations` 字段; 前端选主题后风格 select ⭐ top-3 + ⚠ avoid; 12 个新 test |
| `519e8cf` | bench_tick --theme/--style + RUNBOOK | 标准化 3-seed 入口 (steampunk/republic/apocalypse); 6 个新 test |
| `d3a06a0` | cross-seed verdict aggregator + 6 test | 纯数据聚合 (no LLM), drift PASS/WARN/FAIL gate |
| `8213580` | **3-seed cross-theme 长程 stress — 3/3 PASS** | seed1 steampunk 200tick + seed2 republic 100tick + seed3 apocalypse 100tick, 全部 drift 指标清; Phase 5-B SHIP confirmed |

### 关键数据 (cross-theme drift)

| seed | theme | ticks | tokens | last/first chars | open_loops 稳定 |
| --- | --- | ---: | ---: | ---: | --- |
| seed1 | steampunk_archive (plot-light) | 200 | 1,062,459 | +21.5% | 3-4 |
| seed2 | republic_spy (plot-medium) | 100 | 423,141 | +6.5% | 5 |
| seed3 | apocalypse_wasteland (plot-dense) | 100 | 438,843 | -0.9% | 5 |

stale-skip 率跨 seed 43-43.5% 一致, 完全在 PHASE5_PLAN target window (30-50%).

### 新增 24 个 test (累计 Phase 5 = 83 new test)

* test_recommended_pairs (12) — lru_cache + 缺文件/损坏 graceful + payload schema
* test_bench_tick_theme_args (6) — argparse + 3-seed runbook resolution
* test_verdict_longrange_cross_seed (6) — drift PASS/WARN/INCOMPLETE/ERROR

### ARK 端可观测性 gap (info-only)

`cached_tokens` 字段在 ARK volces `/api/coding/v3` 当前不暴露 (2026-06-17 起).
* Phase 5-A 架构 (SYSTEM bit-identical) 由 unit test 锁定, 不依赖 metadata
* bench MD `cache_hit_rate` 信号失效, 不代表实际未命中
* 切回 DeepSeek 官方 endpoint 或 mimo 可能恢复

详见 `verdict-phase5a-ark-cache-followup.md`.

## 数据 / verdict 文件

* `matrix-bench-1781631506.md` — 主 207/208 OK 矩阵 (commit bf88eb6)
* `matrix-bench-1781662936.md` — Step 2 workplace_drama × classical_chapter 重跑 = 4.67
* `matrix-bench-retro-1781662389.md` — Step 1 全 207 cell retro judge
* `matrix-bench-178166{4242,4681,5119,5583,6057,6521,6944}.md` — Step 5a 7 cell rebench
* `matrix-bench-retro-1781668495.md` — Step 5a' 9 cell 补判 (7 修复 + workplace_drama + 1 漏判)
* `verdict-phase5a-narrator-cache-pilot.md` / `verdict-phase5b-world-stale-skip-pilot.md` / `verdict-phase5-mimo-gate.md` — 早期 verdict (commit 373d3af)
