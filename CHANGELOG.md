# Changelog

本项目采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格,
版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

---

## [2.3.0] — 2026-06-03

### Added — 优先级分层长期记忆 (`backend/memory/memory_store.py`)

针对主 Agent 关注问题清单中的三项:
* **长期记忆与全局一致性崩塌** — 持久化的 `PriorityMemoryStore` (JSON 原子写),
  不依赖单一 LLM 上下文窗口
* **RAG 检索式记忆的致命缺陷** — `RetrievalQuery` 多因子打分
  (importance × recency × reference_count × char_overlap × tag_overlap +
  tier_proximity + protected_bonus), 否定朴素 top-k 余弦相似
* **缺乏分层记忆与优先级机制** — `MemoryRecord` 加 `last_access_tick` /
  `reference_count` / `decay_floor`; `is_protected` 综合 `protected_reason` /
  `TRAUMA_TAGS` (trauma/vow/secret/loss/betrayal) / `reference_count ≥ 3`

### Added — 防退化策略

* `min_l0_or_l1` — 强制 top-k 中至少包含 N 条近期层 (避免"全是 L3 传说"的副作用)
* 同 involved + 邻近 tick_range 桶 dedup, 但空 involved 不参与碰撞
* `effective_importance(current_tick)` — 衰减但有 `decay_floor` 兜底
* `replace_with_compressed(source_ids, new_entry)` — 升级层级时引用计数继承累加

### Changed — Orchestrator 集成

* `Orchestrator.__init__` 接受可选 `memory_store: PriorityMemoryStore`,
  默认从 `tick_state.data_dir` 自动 load
* 新增 `_ingest_events_to_memory(tick, events)` — 阶段 5 后把
  `narrative_value ≥ 4` 的事件入库到 L0
* 阶段 6 后: `events_consumed` 触发 `memory_store.touch()`
  (提升 ref_count, 防遗忘); newly_opened_loops 关联的源事件 `mark_protected()`
* 阶段 7 (`MemoryCompressor`): 真实条目池 + open_loop 保护清单传入, 压缩输出
  `replace_with_compressed` 反写
* `_build_long_term_memory_excerpts(tick, events)` — 新增, 召回 top-5 高优先级
  历史条目, 拼接前缀 `[长期记忆 tier=L1 importance=8] ...` 注入
  `recent_chapter_summaries`, 让 Narrator 跨章节看见保护事件

### Tests

* `backend/tests/test_memory_store.py` — 新增 17 用例 (CRUD / 保护机制 /
  持久化 roundtrip / 多因子打分 / 防退化 / 升级替换 / 长跑不丢保护事实场景)
* 全套 86 条用例通过

---

## [2.2.0] — 2026-06-03

### Added — 质量规范层 (`novel_quality_critique_and_iteration.md` 落地)

* **`backend/agents/quality_spec.py`** — 集中维护规范单一真理源
  * A-G 7 类 50+ 条触发条件 (`TRIGGER_RULES`, `RULES_BY_CODE`)
  * AI 高频套话黑名单 (28 条, A4 触发)
  * 陈词滥调黑名单 (28 条, D3 触发)
  * 展示-而非-告诉对照表 (D4 修订参考)
  * 决策矩阵 (`decide_action`): REWRITE / REVISE / POLISH / RED_TEAM
  * Prompt 片段渲染器: `render_blacklist_block` / `render_show_dont_tell_block`
    / `render_anti_pattern_block` / `render_diversity_block` /
    `render_narrator_quality_block` / `render_full_critique_block`
* **`backend/agents/quality_checks.py`** — 确定性 (无 LLM) 触发检测
  * A1 实词重复 (滑动 2-char 窗口 + stop nominals)
  * A4 AI 套话命中 (含 缓缓地/轻轻地/静静地 的 ≥2 次软触发)
  * A6 段末升华句启发式 (高严重度)
  * A7 开头句式与最近三段命中
  * D2 形容词堆砌 (顿号/逗号分隔启发式)
  * D3 陈词滥调命中
  * E1 句长标准差过低
* **`backend/agents/narrative_critic.py`** — CRITIQUE → REVISE/REWRITE 循环
  * `NarrativeCritic.critique_and_iterate`: 合并确定性 + LLM 触发, 按决策矩阵迭代
  * `MAX_REVISE_ROUNDS` (默认 2) / `MAX_REWRITE_ROUNDS` (默认 2), 上限达到自动降级
  * 高严重度时调用 REWRITE prompt (温度 0.85, 强制维度切换), 中触发时 REVISE
    (温度 0.7, 外科手术式修订, 输出 diffs)
  * 输出 `CritiqueOutput`: `final_text` / `rounds` / `surviving_triggers`
    / `decision_trail` / `new_opening_signature` / `blacklist_to_add`

### Changed — Narrator / Writer prompts 注入硬约束

* **`backend/agents/narrator_agent.py`**
  * `NARRATOR_SYSTEM_PROMPT` 改为字符串拼接, 内嵌
    `render_narrator_quality_block()` 输出的硬黑名单 / 展示-非告诉对照 /
    段落禁忌 / 跨段多样性 4 个 prompt 段
  * 末尾追加 6 条元规则: 不奖励自己 / 代价原则 / 能力守恒 / 未知优先 /
    收尾禁忌 / 直接说情绪 = D4 触发
  * `NarratorAgent.__init__` 增加 `critic` / `enable_critic` 参数, 默认按
    `NARRATOR_ENABLE_CRITIC` 环境变量或 pytest 自动检测决定开关
  * `narrate()` 在 `_parse_output` 之后串接 `_run_critique()`, 调用 critic 循环,
    把最终文本 / 决策轨迹写回 `NarratorOutput`
  * `NarratorOutput` 新增字段: `critique_trace` / `critique_action` /
    `draft_text` / `new_opening_signature` / `blacklist_to_add`
  * 新增滚动状态: `_recent_openings` (最近三段开头签名) /
    `_chapter_blacklist` (本章累计黑名单), 暴露 `reset_chapter_state()` /
    `chapter_blacklist` 给 Orchestrator
* **`backend/agents/writer_agent.py`**
  * 老的 7 条网文风格指令替换为质量规范 block + 元规则
  * 留白原则、代价原则、D4 警告显式写入 system prompt

### Tests

* **`backend/tests/test_quality_spec.py`** — 新增 19 条用例
  * 规范常量自洽 (高严重度 codes 与 rules 一致)
  * 决策矩阵 4 分支
  * 黑名单/陈词滥调/段末升华/开头重复/句长节奏 7 类确定性检查
  * NarrativeCritic 4 路径集成 (clean / medium-only REVISE / high REWRITE /
    上限达到降级)
  * 全套 69 条用例 (含原 50) 通过, 总时长 ~2.3s

### Environment

* `NARRATOR_ENABLE_CRITIC` — `1`/`0` 显式开关, 留空时按 `PYTEST_CURRENT_TEST`
  自动判定 (pytest 关, 生产开)
* `CRITIC_MAX_REVISE_ROUNDS` / `CRITIC_MAX_REWRITE_ROUNDS` — 修订/重写上限
* `CRITIC_ENABLE_LLM` — `0` 时 critic 仅跑确定性检查, 不调 LLM

---

## [2.1.0] — 2026-06-02

将原本并行的两套架构(主目录 v1.x Express+CLI 与 `novel_frame/` v2.x FastAPI+React)
**融合为单一栈**:FastAPI + React/Vite 直接住在项目根,v1.x 文件整体归档到 `old/`。

### Changed

* **目录提升**:`novel_frame/backend/` → `backend/`、`novel_frame/frontend/` → `frontend/`、
  `novel_frame/config.json` 与 `config.example.json` 提到根、`novel_frame/deploy/` → `deploy/`
* **入口统一**:新增根级 `run.py` 与 `start.bat` / `start.sh`,直接 `uvicorn backend.main:app`
  启动,不再需要 `agent_backend` 子进程壳
* **静态资源**:`backend/main.py` 在启动时检测 `frontend/dist/`,存在则直接 mount 到
  Vite base path `/nw/`;dev 模式仍可独立跑 `npm run dev`(Vite 自带 `/api` 代理到 8762)
* **配置桥接**:`backend/config/settings.py` 路径常量从 `<root>/../../config.json` 改为
  `<root>/config.json`,保留 `.env` 优先的 LLM provider 桥接逻辑
* **依赖合并**:删除 `backend/requirements.txt`,根 `requirements.txt` 统一所有运行时依赖,
  移除已归档的多媒体依赖(`edge-tts` / `moviepy` / `dashscope` / `pillow`)

### Removed (实际移动到 `old/`,不丢源码)

* v1.x CLI 入口:`create_novel.py` / `continue_novel.py` / `main.py` / `validate_system.py`
* v1.x 生成器:`core/{generator,chapter_analyzer,background_task,llm_client,embedding_service,novel_manager}.py`
* v1.x 记忆模块:`memory_system/{sliding_window,hierarchical_summary,entity_state,character_relationship,long_term_memory,knowledge_graph}.py`
  以及 `memory_system/*.json` 历史快照
* v1.x Express+ejs 前端 → `old/frontend_express/`
* `agent_backend/` 子进程启动器 → `old/agent_backend/`
* `experimental/` / `utils/` / `tests/` / `multimedia/` / `results/` / `vercel/` / `public/` / `views/` / `temp/`
* 历史规划文档 `IMPLEMENTATION_PLAN.md` / `PROGRESS_SUMMARY.md` / `REFACTORING_*.md` / `docs/MIGRATION.md` → `old/docs/`

### Kept

* `core/config.py` — LLM provider 多源路由(.env → active provider)
* `memory_system/models.py` — Pydantic v2 tick 契约 + 遗留 dataclass
* `evaluation/continuity_v2.py` — `ConsistencyGuardian` 复用的连贯性评估器
* `infinite-novel-multiagent-prompts.md` — 9 agent 设计 prompt 集

---

## [2.0.0] — 2026-06-02

按 [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md)
重构为 9 Agent + 7 阶段 Tick 调度的多智能体模拟系统。

### Added

#### v2.x 核心架构

* **Orchestrator** (`backend/agents/orchestrator.py`) — 纯 Python 7 阶段 tick 调度器,
  无 LLM 调用。支持 pause/resume/inject_event/start_loop
* **WorldSimulator** — 推进时间/天气/自然事件(small 模型),不创造剧情
* **CharacterAgent** — 模板类支持 N 实例,A 级用 strong,B 级用 medium。
  `batch_decide` 用 `asyncio.Semaphore(3)` 限流。严格按 `known_facts` 决策,
  事件可见性过滤(支持 `all` / `all_in_location` / 显式 character_id)
* **NarratorAgent** — 叙事价值评分(0-10 阈值切篇幅:短/中/长/跳过),
  StyleAnchor 注入 system_prompt,动态模型层级(前 100 tick 用最强模型)
* **EventInjector** — 三类事件注入(endogenous/exogenous/dramatic),
  OpenLoop <3 时强制触发
* **Showrunner** — 每 5 tick 评估节奏曲线/冷线索/弧线进度,输出建议
* **MemoryCompressor** — L0→L1→L2→L3 分层压缩(L3 通过 `SummaryTree.legendize()`),
  保护 OpenLoop 源头与创伤性事件
* **ConsistencyGuardian** — 包装 `evaluation/continuity_v2.EnhancedContinuityEvaluator`,
  5 类矛盾扫描(character/time/setting/relationship/item)+ 优先级 A-D
* **NoveltyCritic** — 重复模式检测,recommendations 写入 `TickState.novelty_warnings`
* **ActionResolver** (`nf_core/action_resolver.py`) — 纯 Python 行动冲突解析,
  独占类(fight/take/claim/...) 按 (tier, goal_priority) 仲裁
* **PromptBuilder** (`nf_core/prompt_builder.py`) — Token 自适应裁剪

#### 数据契约(13 个 Pydantic v2 模型)

* `WorldState` / `TickLocation` / `Faction`
* `CharacterProfile` / `CharacterState` / `Goal` / `Relationship`
* `Event` / `OpenLoop` / `MemoryEntry` / `StyleAnchor` / `CharacterAction` / `TickSummary`
* 6 个 Literal 类型 + 遗留 dataclass 完整保留

#### 持久化

* **TickState** — JSON 原子写(`tempfile.mkstemp + os.replace`)
* **TickDB** — SQLite WAL,tick_log + events 两表
* **SummaryTree** — 新增 `persist_to_disk` / `load_from_disk` / `legendize` / `prune_nodes`

#### API + 测试

* `api/tick_routes.py` — 14 条 REST 端点
* `bootstrap_prompts.py` — 5 prompt 冷启动 CLI
* 50 个测试通过(P0/P1/P2/P3 集成 + 单元测试)

### Fixed

* SummaryTree 重启后摘要丢失(P0 bug)
* OpenLoop 失控风险(默认 `max_age_ticks=200` + 每 tick reap)

---

## [1.x] — 2026 之前

历史 v1.x 行为:`NovelGenerator` 章节驱动,五层记忆模块,Express + EJS 前端,
spawn Python 子进程。详见 `old/docs/` 与 git history。
