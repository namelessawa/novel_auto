# 无限小说生成系统 (Infinite Novel Generator)

> **v2.0 多 Agent 重构** — 从单体 `NovelGenerator` (章节驱动) 升级为
> 9 Agent + 7 阶段 Tick 调度的多智能体模拟系统(故事驱动)。
> 基于 [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md)
> 的设计哲学:**故事是模拟的副产品,Narrator 选择性讲述**。

> v1.x (NovelGenerator) 仍保留为 fallback,详见 [docs/MIGRATION.md](./docs/MIGRATION.md)。

---

## 设计哲学(v2.x)

1. **故事是模拟的副产品**:不让 agent 去"写下一章",而是让一群有目标的角色在
   有规则的世界里活动,Narrator 选择性叙述
2. **Narrator 的品味是质量瓶颈**:Narrator 决定 tick 里哪些事件值得讲述,沉默是合法选项
3. **角色只能用自己知道的信息**:CharacterAgent 严格按 `known_facts` + 可见事件决策
4. **主动遗忘是 feature**:L0→L1→L2→L3 分层压缩,远古事件传说化失真
5. **冲突保留池不能为零**:Showrunner 维护 ≥3 个开放伏笔,EventInjector 自动补充

---

## 架构总览

```
                       Orchestrator (纯 Python,无 LLM)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   WorldSimulator       CharacterAgent×N        Narrator
        │                     │                     │
        │            ActionResolver               (品味决定是否产出)
        │                     │                     │
        └──→ Event Stream ←───┘                     ▼
                  ▲                            [章节文本]
                  │
        ┌─────────┴──────────┐
        │                    │
   EventInjector        Showrunner
   (3 类事件注入)       (节奏 + 冲突保留)
        │                    │
        └─────┬──────────────┘
              │
              ▼
        TickState 持久化(JSON 原子写)
        TickDB 日志(SQLite WAL)
              │
        ┌─────┴──────────────────────┐
        ▼                            ▼
  MemoryCompressor          ConsistencyGuardian
  (L0→L1→L2→L3 压缩)        (5 类矛盾扫描)
        ▲                            ▲
        │                            │
        └─────────  NoveltyCritic ───┘
                 (重复模式检测)
```

### 9 个 Agent + 7 阶段 Tick 循环

| # | Agent | 频率 | LLM | 职责 |
|---|-------|------|-----|------|
| 0 | **Orchestrator** | 每 tick | ❌ 纯调度 | 协调 7 阶段流程,无创造力 |
| 1 | **WorldSimulator** | 每 tick | ✅ small | 推进时间/天气/社会演化 |
| 2 | **EventInjector** | 3-5 tick | ✅ medium | 内生/外生/戏剧事件注入 |
| 3 | **CharacterAgent×N** | 每 tick | ✅ A=strong / B=medium | 单角色基于 known_facts 决策 |
| 4 | **ActionResolver** | 每 tick | ❌ 纯逻辑 | 解析独占行动冲突(fight/take) |
| 5 | **Narrator** | 每 tick | ✅ strongest→medium | 选材 + 写作,可主动沉默 |
| 6 | **Showrunner** | 每 5 tick | ✅ medium | 节奏曲线 + 冷线索 + 弧线监控 |
| 7 | **MemoryCompressor** | 每 50 tick | ✅ small | L0→L1→L2→L3 压缩 + 传说化 |
| 8 | **ConsistencyGuardian** | 每 30 tick | ✅ continuity_v2 | 5 类矛盾扫描 |
| 9 | **NoveltyCritic** | 每 20 tick | ✅ small | 重复模式检测,反馈给 Narrator |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt

# 前端
cd frontend && npm install && cd ..
```

### 2. 配置 LLM 密钥

复制 `.env.example` → `.env`,填入 active provider 的密钥:

```bash
LLM_PROVIDER=deepseek          # deepseek | mimo | custom
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

或通过前端 `/api/config` 配置(运行 `cd frontend && npm start` 访问)。

### 3. 启动后端 (v2.x tick 架构)

```bash
# (可选) 切换到具体小说数据目录
$env:ACTIVE_NOVEL_ID="mountain"

# 启动 FastAPI 后端 (内部 subprocess 隔离启动 novel_frame)
python -m agent_backend --port 8000

# 检测后端是否就绪
curl http://127.0.0.1:8000/api/tick/status
```

### 4. 冷启动一个新世界

```bash
# 5 个 bootstrap prompt 自动生成 WorldState + 角色 + 伏笔 + 风格锚点
python -m novel_frame.backend.bootstrap_prompts \
    --novel-id mountain \
    --seed "宋代仿古,边境与中央的张力,存在低调方术传统" \
    --positioning "古典含蓄、心理白描、节奏舒缓" \
    --references "Le Guin / 古龙"
```

bootstrap 完成后:

```bash
# 推进一个 tick(根据 Narrator 品味,可能产出叙述也可能沉默)
curl -X POST http://127.0.0.1:8000/api/tick/run

# 查看当前 tick 状态
curl http://127.0.0.1:8000/api/tick/status

# 浏览历史 tick
curl http://127.0.0.1:8000/api/tick/history?last_n=20
```

### 5. 前端控制面板

```bash
cd frontend && npm start
```

* `http://localhost:8080/` — v1.x 创建/续写主页(自动检测 tick 后端,
  优先用 v2.x;后端不可达时 fallback v1.x spawn Python)
* `http://localhost:8080/tick` — v2.x **Tick 控制面板**(推进/暂停/注入事件/
  Showrunner 视角/OpenLoop 列表/Novelty 警告)

### 6. CLI 入口(向后兼容)

```bash
# v2.x: 优先调用 tick 后端,fallback 到 v1.x NovelGenerator
python create_novel.py "我的小说"
python continue_novel.py "我的小说"

# 强制 v1.x legacy 路径
LEGACY_GENERATOR=1 python create_novel.py "我的小说"

# 续写时单次推进多个 tick
TICKS_TO_RUN=10 python continue_novel.py
```

---

## tick API 速查

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/tick/status` | 当前 tick / 暂停态 / OpenLoop 数 |
| POST | `/api/tick/run` | 推进 1 个 tick (返回 TickSummary) |
| POST | `/api/tick/pause` | 暂停后续自动循环 |
| POST | `/api/tick/resume` | 恢复 |
| POST | `/api/tick/inject-event` | 手动注入 Event |
| GET | `/api/tick/open-loops` | 当前开放伏笔列表(按 urgency 降序) |
| POST | `/api/tick/open-loops` | 管理员手动新增 OpenLoop |
| DELETE | `/api/tick/open-loops/:id` | 关闭 OpenLoop |
| GET | `/api/tick/history?last_n=20` | 最近 N 个 TickSummary (TickDB) |
| GET | `/api/tick/event-stats?last_n_ticks=50` | Showrunner 视角的事件统计 |
| GET | `/api/tick/action-patterns?last_n_ticks=100` | NoveltyCritic 视角的重复模式 |
| GET | `/api/tick/style-anchors?top_k=20` | 风格锚点列表 |
| GET | `/api/tick/character-states` | 全部 CharacterState |
| GET | `/api/tick/novelty-warnings` | NoveltyCritic 输出 |

Express 前端透传 `/api/tick/*` 到 FastAPI 后端。

---

## 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 包名冲突 | `novel_frame/backend/core/` 重命名为 `nf_core/`,删除重复 models.py | 一次性消除 import 二义性 |
| 数据契约 | Pydantic v2 (与遗留 dataclass 并存) | FastAPI 原生集成,`model_dump_json` 省手写 |
| Tick 日志 | SQLite WAL | O(log n) 查询,单文件无独立进程 |
| 状态持久化 | JSON + `tempfile.mkstemp + os.replace` 原子写 | 防止崩溃留下半截文件 |
| Narrator 模型 | 前 100 tick 用最强模型,之后切换到中等模型 | StyleAnchor 维持文风,降低 70% 成本 |
| Narrator 沉默 | 事件总价值 <5 时跳过 | "沉默是节奏,选择是品味" |
| Character 并发 | `asyncio.Semaphore(3)` | 防 LLM API 限速,默认 3 路并行 |
| OpenLoop 失控 | `max_age_ticks=200` 默认 + Orchestrator 每 tick reap | 防止 prompt 无限膨胀 |
| 前端集成 | Express 反代 FastAPI + 保留 spawn 作为 fallback | 现有 UI 不重写,向后兼容 |
| Bootstrap | CLI (`bootstrap_prompts.py`) | 前端向导留待 P4 |

---

## 持久化分层

| 层 | 存储 | 内容 |
|----|------|------|
| 1 | SQLite WAL `ticks.db` | tick_log + events 两表,按 tick_id 主键 |
| 2 | JSON `tick_state.json` | WorldState / CharacterProfile×N / CharacterState×N / OpenLoop / StyleAnchor / novelty_warnings |
| 3 | JSON `summary_tree.json` | 分层摘要 + L3 传说 |
| 4 | NetworkX JSON `knowledge_graph.json` + `snapshots/` | 实体/关系图 + 每 50 tick 快照 |
| 5 | ChromaDB | 向量索引(L0 事件 / L1 摘要) |
| 6 | 文本文件 `narratives/tick_NNNNNN.txt` | Narrator 产出 |

---

## 项目结构(v2.x)

```
novel_auto/
├── .env                              ← LLM 凭据(唯一来源)
├── create_novel.py                   ← v2.x HTTP 客户端(fallback v1.x)
├── continue_novel.py                 ← v2.x HTTP 客户端
├── core/                             ← v1.x legacy + 零改动配置层
│   ├── config.py                     ← 多提供商路由
│   ├── llm_client.py                 ← OpenAI SDK 包装
│   ├── embedding_service.py
│   ├── novel_manager.py
│   ├── generator.py                  ← LEGACY: NovelGenerator
│   ├── chapter_analyzer.py           ← LEGACY: ChapterAnalyzer
│   └── background_task.py            ← BackgroundTaskManager 保留
├── memory_system/                    ← 数据契约 + v1.x 持久化
│   ├── models.py                     ← Pydantic v2 tick 契约 + 遗留 dataclass
│   ├── sliding_window.py             ← +get_sections() 适配器
│   ├── hierarchical_summary.py       ← +L1/L2/L3 getters
│   ├── entity_state.py               ← +EntityStateAdapter
│   ├── character_relationship.py     ← +RelationAnalyzer (情感向量)
│   ├── knowledge_graph.py            ← +get_character_state/get_world_state_snapshot
│   └── long_term_memory.py
├── evaluation/
│   └── continuity_v2.py              ← ConsistencyGuardian 复用此评估器
├── experimental/                     ← 隔离目录,未集成
├── agent_backend/                    ← subprocess 隔离启动器
│   └── __main__.py
├── novel_frame/
│   └── backend/
│       ├── main.py                   ← FastAPI 入口 + tick_runtime 装配
│       ├── tick_runtime.py           ← Orchestrator 单例容器
│       ├── bootstrap_prompts.py      ← 5 prompt 冷启动 CLI
│       ├── nf_core/                  ← 改名自 core/ 解决冲突
│       │   ├── llm_client.py
│       │   ├── action_resolver.py    ← 行动冲突解析(纯 Python)
│       │   └── prompt_builder.py     ← Token 自适应裁剪
│       ├── agents/
│       │   ├── orchestrator.py       ← 7 阶段 tick 调度
│       │   ├── world_simulator.py
│       │   ├── character_agent.py    ← 模板类 + batch_decide 并发
│       │   ├── narrator_agent.py
│       │   ├── event_injector.py
│       │   ├── showrunner.py
│       │   ├── memory_compressor.py
│       │   ├── consistency_guardian.py
│       │   ├── novelty_critic.py
│       │   ├── outline_agent.py      ← v1.x 节级管线(legacy)
│       │   ├── retrieval_agent.py
│       │   ├── validation_agent.py
│       │   ├── writer_agent.py
│       │   └── update_agent.py
│       ├── memory/
│       │   ├── tick_state.py         ← TickState 持久化容器
│       │   ├── summary_tree.py       ← 持久化修复 + legendize
│       │   └── working_memory.py
│       ├── persistence/
│       │   └── tick_db.py            ← SQLite WAL
│       ├── graph/knowledge_graph.py
│       ├── vector/vector_store.py
│       ├── pipeline/engine.py        ← v1.x 节级管线
│       ├── api/
│       │   ├── routes.py             ← v1.x REST + SSE
│       │   └── tick_routes.py        ← v2.x tick 控制 API
│       └── tests/                    ← 50 个测试
├── frontend/
│   ├── server.js                     ← Express 反代 FastAPI + fallback spawn
│   └── views/
│       ├── index.ejs                 ← v1.x 主页
│       └── tick.ejs                  ← v2.x Tick 控制面板
└── docs/
    └── MIGRATION.md                  ← v1.x → v2.x 迁移指南
```

---

## 测试

50 个测试,2.8s 全过:

```bash
cd novel_frame/backend
python -m pytest tests/ -v
```

| 测试文件 | 数量 | 覆盖 |
|----------|------|------|
| `test_knowledge_graph.py` | 7 | KnowledgeGraph CRUD + 快照 + 回滚 |
| `test_working_memory.py` | 4 | WorkingMemory ring buffer + eviction |
| `test_summary_tree_persistence.py` | 9 | 持久化 + 原子写 + legendize 兜底 |
| `test_tick_state.py` | 8 | TickState + OpenLoop reap + arc_status |
| `test_action_resolver.py` | 7 | 冲突解析(tier / goal priority) |
| `test_orchestrator_p0.py` | 5 | 单 tick 全链路 + tick 跨进程恢复 |
| `test_orchestrator_p1.py` | 4 | EventInjector / Showrunner cadence / NoveltyCritic |
| `test_prompt_builder.py` | 6 | Token 预算 + 优先级裁剪 |

---

## 配置参考

### LLM 提供商

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_PROVIDER` | `deepseek` | deepseek / mimo / custom |
| `LLM_MAX_TOKENS` | 8192 | 共享 max_tokens |
| `LLM_TEMPERATURE` | 0.7 | 共享 temperature |
| `LLM_TIMEOUT` | 120 | API 超时(秒) |
| `DEEPSEEK_*` | — | DeepSeek 配置 |
| `MIMO_*` | — | MiMo(小米)配置 |
| `CUSTOM_*` | — | 任意 OpenAI 兼容端点 |

### v2.x tick 行为

| 变量 | 默认 | 说明 |
|------|------|------|
| `ACTIVE_NOVEL_ID` | `default` | 当前小说 id(决定数据目录) |
| `ACTIVE_NOVEL_DATA_DIR` | — | 显式数据目录路径(覆盖 ACTIVE_NOVEL_ID) |
| `MAIN_TRACKING_CHARACTER_ID` | — | Narrator 默认跟随的视角角色 |
| `NARRATOR_STRONG_MODEL_TICKS` | 100 | 前 N tick 用最强模型 |
| `CHARACTER_AGENT_CONCURRENCY` | 3 | Semaphore 并发上限 |
| `DISABLE_TICK_RUNTIME` | `0` | `1` 时禁用 tick runtime(纯 legacy) |
| `TICK_BACKEND_URL` | `http://127.0.0.1:8000` | CLI/前端代理目标 |
| `LEGACY_GENERATOR` | `0` | `1` 时 CLI 强制 v1.x |
| `TICKS_TO_RUN` | 1 | continue_novel.py 单次推进 tick 数 |

### v1.x legacy

| 变量 | 默认 | 说明 |
|------|------|------|
| `SLIDING_WINDOW_MAX_TOKENS` | 2500 | 短期记忆窗口 |
| `CONTINUITY_THRESHOLD` | 80.0 | 续写连续性阈值 |
| `ENABLE_MULTIMEDIA` | false | 启用 TTS/图片/视频 |
| `DASHSCOPE_API_KEY` | — | 阿里云 DashScope (图片) |
| `NOVEL_TOPIC` | — | v1.x 主题(向后兼容) |
| `NOVEL_CUSTOM_PROMPT` | — | 续写时的自定义提示 |

---

## 文档

* [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md)
  — 9 agent 完整 prompt 集 + 设计哲学(必读)
* [`docs/MIGRATION.md`](./docs/MIGRATION.md) — v1.x → v2.x 迁移路径
* [`CHANGELOG.md`](./CHANGELOG.md) — 完整版本历史
* [`CLAUDE.md`](./CLAUDE.md) — Claude Code 工作指南
* [`novel_frame/backend/tests/`](./novel_frame/backend/tests/) — 50 个测试,即文档

---

## 故障排除

### `/api/tick/*` 返回 503

后端未启动或未 bootstrap:

```bash
# 1. 检查后端
curl http://127.0.0.1:8000/

# 2. 启动后端
python -m agent_backend --port 8000

# 3. bootstrap 一个世界
python -m novel_frame.backend.bootstrap_prompts --novel-id test --seed "..."
```

### Narrator 总是沉默 (`narrator_produced_text=false`)

设计如此 — 事件总价值 <5 时 Narrator 跳过。若长期沉默:

* 通过 `/api/tick/inject-event` 注入高 `narrative_value` 事件
* 检查 `/api/tick/open-loops` 是否 ≥3
* 在 tick 控制面板的"手动注入事件"表单输入戏剧事件

### tick 后端启动失败

检查 `novel_frame/backend/config/settings.py` 的 config.json:

```bash
cp novel_frame/config.example.json novel_frame/config.json
```

settings.py 优先桥接主项目 `.env` 的 active provider,config.json 只在 .env 不可用时兜底。

### 终端乱码 (Windows)

```bash
chcp 65001
```

或确保所有 Python 入口的 `sys.stdout` 已用 `io.TextIOWrapper(..., encoding='utf-8')` 包装(`create_novel.py` / `continue_novel.py` / `bootstrap_prompts.py` 都已包含)。

---

## 许可证

仅供学习与研究使用。
