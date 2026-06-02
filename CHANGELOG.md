# Changelog

本项目采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格,
版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

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
  Vite base path `/nw/`;dev 模式仍可独立跑 `npm run dev`(Vite 自带 `/api` 代理到 8000)
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
