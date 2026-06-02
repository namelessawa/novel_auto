# Migration Guide — v1.x (NovelGenerator) → v2.x (Tick Architecture)

本文档记录 2026-06 重构的范围,以及旧入口向新 tick 架构的迁移路径。

---

## 摘要

v2.x 引入 9 agent + 7 阶段 tick 调度的多 agent 架构(基于
[`infinite-novel-multiagent-prompts.md`](../infinite-novel-multiagent-prompts.md))。
设计哲学:

> 故事是模拟的副产品。不要让 agent 去"写下一章",让一群有目标的 agent
> 在一个有规则的世界里活动,然后让 Narrator 选择性地讲述。

v1.x 的 `NovelGenerator` 单体类(章节驱动) → v2.x 的 `Orchestrator + 9 agents`
(tick 驱动 + 沉默叙述)。两套架构**并存运行**,旧入口逐步退役。

---

## 9 agent + 7 阶段

```
                       Orchestrator (纯 Python,无 LLM)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   WorldSimulator      CharacterAgent×N        Narrator
        │                     │                     │
        └──────► EventInjector ◄─────────────  Showrunner
                       │
                       ▼
                 [tick events]
                       │
        ┌──────────────┴───────────────┐
        ▼                              ▼
  MemoryCompressor         ConsistencyGuardian
                                       ▲
                                       │
                                NoveltyCritic
```

tick 频率:

| 频率           | Agent                                         |
|----------------|-----------------------------------------------|
| 每 tick        | Orchestrator / WorldSimulator / CharacterAgent / Narrator |
| 每 3-5 tick    | EventInjector / Showrunner                    |
| 每 20-50 tick  | MemoryCompressor (50) / ConsistencyGuardian (30) / NoveltyCritic (20) |

---

## 模块映射表

### 零改动复用

| 模块                                     | 新角色                             |
|------------------------------------------|------------------------------------|
| `core/config.py`                         | 所有 agent 的配置入口              |
| `core/llm_client.py`                     | LLM 调用层                         |
| `core/embedding_service.py`              | RetrievalAgent 嵌入服务            |
| `core/novel_manager.py`                  | manifest CRUD                      |
| `agent_backend/`                         | subprocess 隔离启动器              |
| `novel_frame/backend/graph/knowledge_graph.py` | KnowledgeGraph                     |
| `novel_frame/backend/vector/vector_store.py`   | VectorStore (RAG)                  |
| `novel_frame/backend/agents/retrieval_agent.py`| 上下文组装                         |

### 重命名

| v1.x                                          | v2.x                                            |
|-----------------------------------------------|-------------------------------------------------|
| `novel_frame/backend/core/llm_client.py`      | `novel_frame/backend/nf_core/llm_client.py`     |
| `novel_frame/backend/core/models.py` (重复)   | **删除**,统一用 `memory_system/models.py`       |
| `from core.X import Y` (in novel_frame)       | `from nf_core.X import Y` 或 `from memory_system.X import Y` |

### 新增模块

| 路径                                                      | 角色                          |
|-----------------------------------------------------------|-------------------------------|
| `novel_frame/backend/agents/orchestrator.py`              | Orchestrator (7 阶段调度)     |
| `novel_frame/backend/agents/world_simulator.py`           | WorldSimulator                |
| `novel_frame/backend/agents/character_agent.py`           | CharacterAgent (模板类)       |
| `novel_frame/backend/agents/narrator_agent.py`            | Narrator                      |
| `novel_frame/backend/agents/event_injector.py`            | EventInjector                 |
| `novel_frame/backend/agents/showrunner.py`                | Showrunner                    |
| `novel_frame/backend/agents/memory_compressor.py`         | MemoryCompressor              |
| `novel_frame/backend/agents/consistency_guardian.py`      | ConsistencyGuardian (+ Adapter) |
| `novel_frame/backend/agents/novelty_critic.py`            | NoveltyCritic                 |
| `novel_frame/backend/memory/tick_state.py`                | TickState 持久化容器          |
| `novel_frame/backend/persistence/tick_db.py`              | SQLite WAL tick 日志          |
| `novel_frame/backend/nf_core/action_resolver.py`          | 行动冲突解析                  |
| `novel_frame/backend/tick_runtime.py`                     | Orchestrator 装配单例         |
| `novel_frame/backend/api/tick_routes.py`                  | tick 控制 REST API            |
| `novel_frame/backend/bootstrap_prompts.py`                | 5 prompt 冷启动 CLI           |

### 扩展(向后兼容)

| 模块                                                | 扩展                                           |
|-----------------------------------------------------|------------------------------------------------|
| `memory_system/models.py`                           | 新增 13 个 Pydantic v2 tick 契约 + 6 个 Literal 类型 |
| `novel_frame/backend/memory/summary_tree.py`        | 新增 `persist_to_disk` / `load_from_disk` / `legendize` / `prune_nodes` |
| `novel_frame/backend/main.py`                       | FastAPI startup/shutdown 装配 tick runtime    |

### Legacy(添加注释,不删除)

| 模块                              | LEGACY 注释                                                                                  |
|-----------------------------------|----------------------------------------------------------------------------------------------|
| `core/generator.py`               | NovelGenerator 拆分为 Orchestrator + Narrator + MemoryCompressor + ChapterPersistence       |
| `core/chapter_analyzer.py`        | 功能被 `agents/update_agent.py` UpdateAgent 覆盖                                              |
| `core/background_task.py`         | `ChapterPostProcessor` LEGACY, `BackgroundTaskManager` 保留(多媒体路径)                       |
| `create_novel.py` / `continue_novel.py` | 旧 CLI 入口保留,P3 改为 HTTP 客户端包装                                                  |

---

## 新数据契约(Pydantic v2)

`memory_system/models.py` 同时承载两套契约,刻意分层:

* **遗留 dataclass**: `Entity` / `Relation` / `Section` / `ActionPlan` /
  `ValidationResult` / `GraphSnapshot` - knowledge_graph + 旧管线使用
* **tick Pydantic**: `WorldState` / `Faction` / `TickLocation` / `CharacterProfile` /
  `CharacterState` / `Goal` / `Relationship` / `Event` / `OpenLoop` /
  `MemoryEntry` / `StyleAnchor` / `CharacterAction` / `TickSummary`

跨边界传值优先使用 Pydantic,FastAPI 原生集成 + `model_dump_json` 简化持久化。

---

## 持久化分层

| 层 | 存储                         | 内容                              |
|----|------------------------------|-----------------------------------|
| 1  | SQLite (WAL) `ticks.db`      | tick_log + events 表              |
| 2  | JSON `tick_state.json`       | WorldState / CharacterProfile / CharacterState / OpenLoop / StyleAnchor / novelty_warnings |
| 3  | JSON `summary_tree.json`     | 分层摘要 + L3 传说                |
| 4  | NetworkX JSON `knowledge_graph.json` + `snapshots/` | 实体/关系图 + 每 50 tick 快照 |
| 5  | ChromaDB                     | 向量索引(L0 事件 / L1 摘要)       |
| 6  | 文本文件 `narratives/tick_NNNNNN.txt` | Narrator 产出的章节文本           |

所有 JSON 写都用 `tempfile.mkstemp` + `os.replace` 原子写。

---

## 新启动流程

### 冷启动(新世界)

```powershell
# 1. 运行 bootstrap CLI - 5 prompt 生成初始世界 + 角色 + 伏笔 + 风格
python -m novel_frame.backend.bootstrap_prompts `
    --novel-id mountain `
    --seed "宋代仿古,边境与中央的张力,存在低调方术传统" `
    --positioning "古典含蓄、心理白描、节奏舒缓" `
    --references "Le Guin / 古龙"

# 2. 启动 backend(自动接管已 bootstrap 的世界)
$env:ACTIVE_NOVEL_DATA_DIR = "novel_frame/backend/data/novels/mountain"
$env:MAIN_TRACKING_CHARACTER_ID = "char_alice"
python -m agent_backend --port 8000
```

### 控制 tick 循环

```bash
# 查看状态
curl http://localhost:8000/api/tick/status

# 手动推进 1 个 tick
curl -X POST http://localhost:8000/api/tick/run

# 暂停
curl -X POST http://localhost:8000/api/tick/pause

# 手动注入戏剧事件
curl -X POST http://localhost:8000/api/tick/inject-event \
  -H 'Content-Type: application/json' \
  -d '{"description":"陌生人在城门留下血书","narrative_value":9,"visible_to":["char_alice"]}'

# 查看开放伏笔
curl http://localhost:8000/api/tick/open-loops

# 查看 Showrunner 视角的事件统计
curl http://localhost:8000/api/tick/event-stats?last_n_ticks=50

# 查看历史 tick 摘要
curl http://localhost:8000/api/tick/history?last_n=20
```

### 旧 CLI(向后兼容)

```bash
python create_novel.py     # 仍可用,走 NovelGenerator (LEGACY)
python continue_novel.py
```

P3 阶段会改为 HTTP 客户端调用 tick 后端。

---

## 关键设计决策(用户确认过)

1. **nf_core 重命名**: `novel_frame/backend/core/` → `novel_frame/backend/nf_core/`,
   消除与主项目 `core/` 的命名冲突
2. **Pydantic v2**: tick 契约统一用 Pydantic,FastAPI 原生集成,旧 dataclass 共存
3. **Express 反代 FastAPI SSE**: 前端保留,后续 P3 spawn Python 子进程改为 HTTP 代理
4. **前端引导 bootstrap**: 现在由 CLI 触发,P3 增加 Express 向导页
5. **SQLite WAL**: tick 日志,无独立进程,O(log n) 查询
6. **Narrator 动态模型**: 默认前 100 tick 用最强模型,之后切换到中等模型
   (`NARRATOR_STRONG_MODEL_TICKS` 环境变量调节)
7. **CharacterAgent 并发 Semaphore(3)**: 防 LLM API 限速
   (`CHARACTER_AGENT_CONCURRENCY` 调节)

---

## 已知风险与缓解

| 风险                              | 缓解                                                          |
|-----------------------------------|---------------------------------------------------------------|
| SummaryTree 重启后摘要丢失 (P0)   | ✅ 已修: 新增 `persist_to_disk` + 原子写                       |
| 双 core 包名冲突                  | ✅ 已修: nf_core 重命名 + models.py 去重                       |
| OpenLoop 数量失控                 | ✅ OpenLoop.max_age_ticks 默认 200,Orchestrator 每 tick reap |
| tick 状态原子性                   | ✅ TickState/SummaryTree 全部 `tempfile.mkstemp + os.replace` |
| CharacterAgent 并行成本           | ✅ Semaphore(3) 默认; A 级用 'strong', B 级用 'medium'         |
| 事件可见性扩展性                  | ✅ 支持 "all" / "all_in_location" / 显式 character_id          |

---

## 测试覆盖

`novel_frame/backend/tests/` 共 44 个测试,2.8s 全过:

| 测试文件                                    | 数量 | 覆盖                                     |
|---------------------------------------------|------|------------------------------------------|
| `test_knowledge_graph.py`                   | 7    | KnowledgeGraph CRUD + 快照 + 回滚         |
| `test_working_memory.py`                    | 4    | WorkingMemory ring buffer + eviction      |
| `test_summary_tree_persistence.py`          | 9    | 持久化 + 原子写 + legendize 兜底         |
| `test_tick_state.py`                        | 8    | TickState + OpenLoop reap + arc_status   |
| `test_action_resolver.py`                   | 7    | 冲突解析 (tier / goal priority)          |
| `test_orchestrator_p0.py`                   | 5    | 单 tick 全链路 + tick 跨进程恢复          |
| `test_orchestrator_p1.py`                   | 4    | EventInjector 触发 + TickDB + Showrunner cadence + NoveltyCritic |

---

## 待办(P3)

* Express 前端: spawn Python 改为 HTTP 代理 FastAPI SSE
* Express 新增 tick 控制 UI(启动/暂停/注入事件/查看 OpenLoop)
* Express 新增 bootstrap 向导页(seed/positioning/references 表单)
* memory_system 旧适配器(EntityStateAdapter / RelationAnalyzer / sliding_window.get_sections)
* create_novel.py / continue_novel.py 改为 HTTP 客户端
* PromptBuilder 独立工具类(从 generator.py 提取)
