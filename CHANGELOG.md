# Changelog

本项目采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格,
版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

---

## [2.0.0] — 2026-06-02

按 [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md)
重构为 9 Agent + 7 阶段 Tick 调度的多智能体模拟系统。

### Added

#### v2.x 核心架构

* **Orchestrator** (`novel_frame/backend/agents/orchestrator.py`) — 纯 Python
  7 阶段 tick 调度器,无 LLM 调用。支持 pause/resume/inject_event/start_loop
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
* **PromptBuilder** (`nf_core/prompt_builder.py`) — Token 自适应裁剪,
  优先级 1 必保留 / 2-3 截断 / 4+ 整段 drop

#### 数据契约(13 个 Pydantic v2 模型)

* `WorldState` / `TickLocation` / `Faction`
* `CharacterProfile` / `CharacterState` / `Goal` / `Relationship`
* `Event` / `OpenLoop` / `MemoryEntry` / `StyleAnchor`
* `CharacterAction` / `TickSummary`
* 6 个 Literal 类型(`ImportanceTier` / `EventKind` / `MemoryTier` /
  `ConflictPriority` / `ConflictType` / `OpenLoopType`)
* 遗留 dataclass (Entity / Relation / Section / ActionPlan / ValidationResult /
  GraphSnapshot) 完整保留,两套契约并存

#### 持久化层

* **TickState** (`memory/tick_state.py`) — JSON 原子写(`tempfile.mkstemp + os.replace`),
  封装 WorldState / CharacterProfile×N / CharacterState×N / OpenLoop / StyleAnchor /
  novelty_warnings / last_event_tick
* **TickDB** (`persistence/tick_db.py`) — SQLite WAL 模式,tick_log + events 两表,
  提供 `get_event_stats` / `get_action_patterns` / `get_recent_ticks`
* **SummaryTree** — 新增 `persist_to_disk` / `load_from_disk` / `legendize` /
  `prune_nodes` (**修复 P0 Bug**:重启后摘要丢失)

#### API + UI

* `api/tick_routes.py` — 14 条 REST 端点(status / run / pause / resume /
  inject-event / open-loops / history / event-stats / action-patterns /
  style-anchors / character-states / novelty-warnings)
* `tick_runtime.py` — Orchestrator 单例容器,FastAPI startup/shutdown 自动装配
* `bootstrap_prompts.py` — 5 prompt 冷启动 CLI
  (`python -m novel_frame.backend.bootstrap_prompts --novel-id ... --seed ...`)
* `frontend/views/tick.ejs` — Tick 控制面板(推进/暂停/注入事件/Showrunner
  视角/OpenLoop 列表/事件统计/Novelty 警告/历史 tick 表格)
* `frontend/server.js` — 新增 `/api/tick/*` 透传代理 + `/create-novel` 和
  `/continue-novel` 自动检测 tick 后端

#### memory_system 适配器

* `sliding_window.get_sections()` — 投影为遗留 Section dataclass
* `hierarchical_summary.get_l1_summaries()/get_l2_arcs()/get_l3_outline()`
* `entity_state.EntityStateAdapter` — 旧 dict → tick WorldState / CharacterState
* `character_relationship.RelationAnalyzer` — 情感向量提取 + tension/stability scoring
* `knowledge_graph.get_character_state()/get_world_state_snapshot()`

#### 测试 + 文档

* **50 个测试**通过(P0 P1 P2 P3 共四阶段集成测试 + 单元测试)
* `docs/MIGRATION.md` — v1.x → v2.x 完整迁移指南
* `tests/conftest.py` — `mock_llm` fixture 拦截所有 `nf_core.llm_client.llm_client.chat`,
  测试不依赖真实 LLM
* `tests/test_orchestrator_p0.py` — 单 tick 全链路 + tick 跨进程恢复 + 冲突标注 +
  外部事件注入(5 用例)
* `tests/test_orchestrator_p1.py` — EventInjector 自动触发 / TickDB 持久化 /
  Showrunner cadence / NoveltyCritic 警告写入(4 用例)
* `tests/test_tick_state.py` — OpenLoop reap / arc_status / 持久化 round-trip(8 用例)
* `tests/test_action_resolver.py` — 冲突解析 7 用例
* `tests/test_summary_tree_persistence.py` — 原子写 / legendize 兜底 / prune 9 用例
* `tests/test_prompt_builder.py` — Token 预算 + 优先级裁剪 6 用例

### Changed

* **`novel_frame/backend/core/` → `novel_frame/backend/nf_core/`**:
  消除与主项目 `core/` 包名冲突。13 个 import 路径全部更新。
* **删除 `novel_frame/backend/core/models.py`**:与 `memory_system/models.py`
  完全重复,统一为后者(防类型不匹配 bug)
* `novel_frame/backend/main.py`:新增 startup/shutdown 事件钩子,
  自动装配 tick_runtime,注入到 tick_routes 依赖容器
* `frontend/server.js`:`/create-novel` 和 `/continue-novel` 优先尝试 HTTP 代理
  到 FastAPI,后端不可达 fallback 到原 spawn Python 行为(向后兼容)
* `create_novel.py` / `continue_novel.py`:改写为 HTTP 客户端,
  优先调用 `/api/tick/run`,后端不可达 fallback v1.x NovelGenerator
* `memory_system/models.py`:扩展(不删除遗留 dataclass)新增 tick 契约
* `core/generator.py` / `core/chapter_analyzer.py` / `core/background_task.py`:
  添加 `LEGACY` 注释,标明替代位置

### Fixed

* **P0 Bug**:`novel_frame/backend/memory/summary_tree.py` 没有 `persist_to_disk`,
  重启 FastAPI 后所有 LLM 压缩历史摘要丢失,回退为"故事尚未开始" → 修复
* **OpenLoop 失控风险**:`OpenLoop.max_age_ticks=200` 默认 + Orchestrator
  每 tick `reap_stale_open_loops`,防止 prompt 无限膨胀
* **tick 状态原子性**:TickState + SummaryTree 全部用
  `tempfile.mkstemp + os.replace` 原子写

### Deprecated

* `core.NovelGenerator` — 706 行单体类,被 Orchestrator + NarratorAgent +
  MemoryCompressor 分别替代
* `core.ChapterAnalyzer` — 被 `agents/update_agent.UpdateAgent` 覆盖
* `core.ChapterPostProcessor` — 记忆更新逻辑已 noop,仅多媒体路径活跃
* `create_novel.py` / `continue_novel.py` 旧 CLI 行为 — 仍作为 fallback 保留,
  P4 可考虑删除

### Removed

* `novel_frame/backend/core/__init__.py`
* `novel_frame/backend/core/llm_client.py`(移到 nf_core/)
* `novel_frame/backend/core/models.py`(完全重复,删除)

---

## [1.x] — 2026 之前

历史 v1.x 行为:`NovelGenerator` 章节驱动,五层记忆模块(`SlidingWindowMemory` +
`EntityStateTracker` + `HierarchicalSummarizer` + `LongTermEventMemory` +
`CharacterRelationshipGraph` + 可选 `KnowledgeGraph`),Express + EJS 前端,
spawn Python 子进程。

v1.x 主要里程碑:

* **阶段三** — `KnowledgeGraph` 引入,NetworkX 实体/关系建模 + 快照/回滚
* **阶段四** — `agent_backend` + `novel_frame` 并行后端引入,
  outline → retrieval → validation → writer → update 节级管线 + SSE
* 多 LLM 提供商支持(DeepSeek / MiMo / Custom OpenAI 兼容)
* 多媒体生成(TTS / 图片 / 视频)
* 多小说 manifest 管理

详见 git history 与 `IMPLEMENTATION_PLAN.md` / `PROGRESS_SUMMARY.md` /
`REFACTORING_REPORT.md`。
