# 无限小说生成系统 (Infinite Novel Generator)

> **v2.1 单栈融合版** — FastAPI + React/Vite 直接住在项目根。
> 9 Agent + 7 阶段 Tick 调度的多智能体模拟系统(故事驱动)。
> 设计哲学来自 [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md):
> **故事是模拟的副产品,Narrator 选择性讲述**。

> v1.x 章节驱动单体生成器已整体归档到 [`old/`](./old/),
> 不再参与运行时,但可作为历史参考。

---

## 设计哲学

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
| 0 | **Orchestrator** | 每 tick | ❌ 纯调度 | 协调 7 阶段流程 |
| 1 | **WorldSimulator** | 每 tick | ✅ small | 推进时间/天气/社会演化 |
| 2 | **EventInjector** | 3-5 tick | ✅ medium | 内生/外生/戏剧事件注入 |
| 3 | **CharacterAgent×N** | 每 tick | ✅ A=strong / B=medium | 单角色基于 known_facts 决策 |
| 4 | **ActionResolver** | 每 tick | ❌ 纯逻辑 | 解析独占行动冲突 |
| 5 | **Narrator** | 每 tick | ✅ strongest→medium | 选材 + 写作,可主动沉默 |
| 6 | **Showrunner** | 每 5 tick | ✅ medium | 节奏曲线 + 冷线索 + 弧线监控 |
| 7 | **MemoryCompressor** | 每 50 tick | ✅ small | L0→L1→L2→L3 压缩 + 传说化 |
| 8 | **ConsistencyGuardian** | 每 30 tick | ✅ continuity_v2 | 5 类矛盾扫描 |
| 9 | **NoveltyCritic** | 每 20 tick | ✅ small | 重复模式检测,反馈 Narrator |

### 优先级分层长期记忆 (v2.3 新增)

> 反 RAG 退化 — 不依赖朴素余弦相似, 多因子打分 + 防退化策略。

`backend/memory/memory_store.py` 提供 `PriorityMemoryStore`:

| 维度 | 公式 | 作用 |
|------|------|------|
| importance_eff | `importance × decay(ticks_since_access) + ref_bonus` | 重要性随时间衰减, 但高引用补偿 |
| recency | `5 / (1 + ticks_since / 100)` | 偏好近期, 但不抹掉远古 |
| char_overlap | `× 4.0` | 角色重叠加成 |
| tag_overlap | `× 3.0` | 情感/主题标签 |
| tier_proximity | L0=+1.0 / L1=+0.5 / L3=-0.5 | 分层近程 |
| protected | `+2.0 if is_protected` | open_loop / trauma / ref≥3 保护 |

防退化:
* `min_l0_or_l1` 强制保留近期层, 避免"全是 L3 传说"
* 同 involved + 邻近 tick 去重 (桶宽 20 tick)
* `replace_with_compressed` 升级时引用计数继承

Orchestrator 集成: 阶段 5 后自动 L0 入库, 阶段 6 后 `events_consumed`
触发 `touch()`, 阶段 7 整池压缩。Narrator 通过 `_build_long_term_memory_excerpts`
拿到 top-5 高优先级历史条目, 跨章节看见保护事件。

### 质量规范层 (v2.2 新增)

> 故事不是"生成",而是 **生成 → 批判 → 修订**。Narrator 每段产出后自动跑
> CRITIQUE → REVISE / REWRITE 循环,直到通过规范或触达上限。

| 模块 | 角色 |
|------|------|
| `backend/agents/quality_spec.py` | 单一真理源 — A-G 7 类 50+ 触发条件、AI 套话黑名单、陈词滥调黑名单、展示-非告诉对照表、决策矩阵 |
| `backend/agents/quality_checks.py` | 确定性 (无 LLM) 检测 — A1/A4/A6/A7/D2/D3/E1 |
| `backend/agents/narrative_critic.py` | CRITIQUE → REVISE / REWRITE 循环, 按 §2.1 决策矩阵迭代 |

**决策矩阵**:

| 触发情况 | 决策 |
|----------|------|
| ≥1 项高严重度 | **REWRITE** — 完全丢稿, 在节奏 / 感官 / 内外比例 / 句长 / 信息密度 至少一维度上切换 |
| 0 高 + ≥3 中 | **REVISE** — 外科手术式修订, 输出 diffs |
| 0 高 + ≤2 中 | **POLISH & ACCEPT** — 微调接受, 黑名单更新 |
| 全部通过 | **RED_TEAM** — 红队复查 (Showrunner/NoveltyCritic 层兜底) |

**环境开关**:

```bash
NARRATOR_ENABLE_CRITIC=1          # 显式开启 (留空时 pytest 关 / 生产开)
CRITIC_MAX_REVISE_ROUNDS=2        # 修订上限
CRITIC_MAX_REWRITE_ROUNDS=2       # 重写上限
CRITIC_ENABLE_LLM=1               # 0 时仅跑确定性检查
```

---

## 快速开始

### 1. 安装依赖

```bash
# Python(运行 + 测试)
pip install -r requirements-dev.txt

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

(也可写到 `config.json` 兜底,但 `.env` 优先。)

### 3. 一键启动前后端

```bash
# Windows
start.bat

# macOS / Linux
./start.sh
```

或分别启动:

```bash
# 后端 (FastAPI, http://127.0.0.1:8762)
python run.py --reload

# 前端 (Vite, http://127.0.0.1:3143/nw/)
cd frontend && npm run dev
```

> Vite dev server 自带 `/api` 代理到 8762;前端访问 backend 的 SSE 与 REST 无需配置 CORS。
> 端口可通过 `config.json` `server.backend_port` / `server.frontend_port` 修改。

### 4. 冷启动一个新世界

```bash
python -m backend.bootstrap_prompts \
    --novel-id mountain \
    --seed "宋代仿古,边境与中央的张力,存在低调方术传统" \
    --positioning "古典含蓄、心理白描、节奏舒缓" \
    --references "Le Guin / 古龙"
```

bootstrap 完成后:

```bash
curl -X POST http://127.0.0.1:8762/api/tick/run
curl http://127.0.0.1:8762/api/tick/status
curl http://127.0.0.1:8762/api/tick/history?last_n=20
```

也可在前端 Tick 控制面板里手动推进、注入事件、查看 OpenLoop。

### 5. 生产部署(SPA + API 同源)

```bash
cd frontend && npm run build && cd ..    # 产物在 frontend/dist/
python run.py                            # FastAPI 自动 mount frontend/dist 到 /nw/
```

访问 `http://<host>:8762/nw/` 即可。`deploy/` 下提供了 nginx 与 systemd 样例。

---

## tick API 速查

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/tick/status` | 当前 tick / 暂停态 / OpenLoop 数 |
| POST | `/api/tick/run` | 推进 1 个 tick (返回 TickSummary) |
| POST | `/api/tick/pause` | 暂停后续自动循环 |
| POST | `/api/tick/resume` | 恢复 |
| POST | `/api/tick/inject-event` | 手动注入 Event |
| GET | `/api/tick/open-loops` | 开放伏笔列表(按 urgency 降序) |
| POST | `/api/tick/open-loops` | 管理员手动新增 OpenLoop |
| DELETE | `/api/tick/open-loops/:id` | 关闭 OpenLoop |
| GET | `/api/tick/history?last_n=20` | 最近 N 个 TickSummary |
| GET | `/api/tick/event-stats?last_n_ticks=50` | 事件统计 |
| GET | `/api/tick/action-patterns?last_n_ticks=100` | 重复模式 |
| GET | `/api/tick/style-anchors?top_k=20` | 风格锚点列表 |
| GET | `/api/tick/character-states` | 全部 CharacterState |
| GET | `/api/tick/novelty-warnings` | NoveltyCritic 输出 |

---

## 持久化分层

| 层 | 存储 | 内容 |
|----|------|------|
| 1 | SQLite WAL `ticks.db` | tick_log + events 两表,按 tick_id 主键 |
| 2 | JSON `tick_state.json` | WorldState / CharacterProfile×N / OpenLoop / StyleAnchor / novelty_warnings |
| 3 | JSON `summary_tree.json` | 分层摘要 + L3 传说 |
| 4 | NetworkX JSON `knowledge_graph.json` + `snapshots/` | 实体/关系图 + 每 50 tick 快照 |
| 5 | ChromaDB | 向量索引(L0 事件 / L1 摘要) |
| 6 | 文本文件 `narratives/tick_NNNNNN.txt` | Narrator 产出 |

所有数据存放在 `backend/data/novels/{novel_id}/`(被 `.gitignore`)。

---

## 项目结构

```
novel_auto/
├── .env                              ← LLM 凭据(优先来源)
├── config.json                       ← memory/vector/server 配置 + LLM 兜底
├── config.example.json
├── run.py                            ← 根级启动入口 (uvicorn backend.main:app)
├── start.bat / start.sh              ← 一键启动后端 + 前端
├── requirements.txt / requirements-dev.txt
├── infinite-novel-multiagent-prompts.md ← 9 agent 设计 prompt 集
├── core/
│   ├── __init__.py
│   └── config.py                     ← 多 provider 路由,backend 通过 importlib 加载
├── memory_system/
│   ├── __init__.py
│   └── models.py                     ← Pydantic v2 tick 契约 + 遗留 dataclass
├── evaluation/
│   ├── __init__.py
│   └── continuity_v2.py              ← ConsistencyGuardian 复用
├── backend/                          ← FastAPI + 9 Agent + Tick 引擎
│   ├── main.py                       ← FastAPI 入口 + 静态资源 mount
│   ├── tick_runtime.py               ← Orchestrator 单例
│   ├── bootstrap_prompts.py          ← 5 prompt 冷启动
│   ├── novel_manager.py
│   ├── config/settings.py            ← 桥接 .env + config.json
│   ├── nf_core/                      ← LLM client + ActionResolver + PromptBuilder
│   ├── agents/                       ← Orchestrator / 9 个 Agent + 节级管线 5 个
│   ├── memory/                       ← TickState / SummaryTree / WorkingMemory
│   ├── persistence/                  ← TickDB (SQLite WAL)
│   ├── graph/                        ← KnowledgeGraph (NetworkX)
│   ├── vector/                       ← VectorStore (ChromaDB)
│   ├── pipeline/                     ← 节级管线
│   ├── api/                          ← routes.py (节级 REST+SSE) + tick_routes.py
│   ├── data/novels/{id}/             ← 运行时数据(gitignored)
│   └── tests/                        ← 50 个测试
├── frontend/                         ← React + Vite 6
│   ├── index.html
│   ├── vite.config.js                ← base=/nw/, /api → 8762 proxy
│   ├── src/
│   │   ├── App.jsx / main.jsx
│   │   ├── pages/ components/ services/ styles/
│   └── package.json
├── deploy/                           ← nginx / systemd 样例
└── old/                              ← v1.x 归档(不参与运行)
    ├── docs/                         ← IMPLEMENTATION_PLAN / MIGRATION / ...
    ├── core/ memory_system/          ← v1 生成器与记忆模块
    ├── experimental/ utils/ tests/   ← 实验性 / 工具 / 旧测试
    ├── multimedia/ results/ vercel/ public/ views/ temp/
    ├── frontend_express/             ← v1 Express+ejs 前端
    ├── agent_backend/                ← v2 subprocess 启动器(已被 run.py 替代)
    └── create_novel.py / continue_novel.py / main.py / validate_system.py
```

---

## 测试

50 个测试,2.8 秒全过:

```bash
python -m pytest backend/tests/ -v
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

### LLM 提供商(`.env`)

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_PROVIDER` | `deepseek` | deepseek / mimo / custom |
| `LLM_MAX_TOKENS` | 8192 | 共享 max_tokens |
| `LLM_TEMPERATURE` | 0.7 | 共享 temperature |
| `LLM_TIMEOUT` | 120 | API 超时(秒) |
| `DEEPSEEK_*` | — | DeepSeek 配置 |
| `MIMO_*` | — | MiMo(小米)配置 |
| `CUSTOM_*` | — | 任意 OpenAI 兼容端点 |

### tick 行为

| 变量 | 默认 | 说明 |
|------|------|------|
| `ACTIVE_NOVEL_ID` | `default` | 当前小说 id(决定数据目录) |
| `ACTIVE_NOVEL_DATA_DIR` | — | 显式数据目录路径(覆盖 ACTIVE_NOVEL_ID) |
| `MAIN_TRACKING_CHARACTER_ID` | — | Narrator 默认跟随的视角角色 |
| `NARRATOR_STRONG_MODEL_TICKS` | 100 | 前 N tick 用最强模型 |
| `CHARACTER_AGENT_CONCURRENCY` | 3 | Semaphore 并发上限 |
| `DISABLE_TICK_RUNTIME` | `0` | `1` 时禁用 tick runtime |
| `AGENT_HOST` / `AGENT_PORT` / `AGENT_RELOAD` / `AGENT_LOG_LEVEL` | — | uvicorn 配置 |

---

## 文档

* [`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md)
  — 9 agent 完整 prompt 集 + 设计哲学(必读)
* [`CHANGELOG.md`](./CHANGELOG.md) — 完整版本历史
* [`CLAUDE.md`](./CLAUDE.md) — Claude Code 工作指南
* [`backend/tests/`](./backend/tests/) — 50 个测试,即文档
* [`old/docs/`](./old/docs/) — v1.x 历史规划文档(MIGRATION / IMPLEMENTATION_PLAN / ...)

---

## 故障排除

### `/api/tick/*` 返回 503

后端未启动或未 bootstrap:

```bash
curl http://127.0.0.1:8762/api/health     # 1. 检查后端是否在跑
python run.py --reload                    # 2. 启动后端
python -m backend.bootstrap_prompts --novel-id test --seed "..."   # 3. bootstrap 一个世界
```

### Narrator 总是沉默 (`narrator_produced_text=false`)

设计如此 — 事件总价值 <5 时 Narrator 跳过。若长期沉默:

* 通过 `/api/tick/inject-event` 注入高 `narrative_value` 事件
* 检查 `/api/tick/open-loops` 是否 ≥3
* 在前端 Tick 控制面板的"手动注入事件"表单输入戏剧事件

### 后端启动失败

确认 `config.json` 存在:

```bash
cp config.example.json config.json
```

`backend/config/settings.py` 优先桥接 `.env` 的 active provider,config.json 只在 .env 不可用时兜底。

### 终端乱码 (Windows)

```bash
chcp 65001
```

---

## 许可证

仅供学习与研究使用。
