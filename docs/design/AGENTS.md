# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

无限小说生成系统 — 单栈 FastAPI + React/Vite 的整书长篇小说生产系统。默认产品路径是
Author production：整书规格与大纲 → 串行章节/分节 Writer → 确定性校验 → 原子提交。
9 Agent + 7 阶段 Tick 世界模拟保留为显式实验功能，其设计哲学来自
[`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md)，但不参与默认
建书、大纲或整书生产。

> 旧章节驱动单体生成器已整体归档到 `old/`，不参与运行时。

## 核心架构

### 默认 Author production

整书契约、持久化、编排与 API 位于 `backend/story/production_*.py`、
`backend/api/production_routes.py` 和 `backend/api/production_control_routes.py`。默认路径
不构建 Tick runtime；完整说明见 [`../FINAL_ARCHITECTURE.md`](../FINAL_ARCHITECTURE.md)。

### 实验性 9 Agent + 7 阶段 Tick 循环

| # | Agent | 频率 | LLM | 路径 |
|---|-------|------|-----|------|
| 0 | Orchestrator | 每 tick | ❌ | `backend/agents/orchestrator.py` |
| 1 | WorldSimulator | 每 tick | small | `backend/agents/world_simulator.py` |
| 2 | EventInjector | 3-5 tick | medium | `backend/agents/event_injector.py` |
| 3 | CharacterAgent×N | 每 tick | A=strong/B=medium | `backend/agents/character_agent.py` |
| 4 | ActionResolver | 每 tick | ❌ | `backend/nf_core/action_resolver.py` |
| 5 | NarratorAgent | 每 tick | strongest→medium | `backend/agents/narrator_agent.py` |
| 6 | Showrunner | 每 5 tick | medium | `backend/agents/showrunner.py` |
| 7 | MemoryCompressor | 每 50 tick | small | `backend/agents/memory_compressor.py` |
| 8 | ConsistencyGuardian | 每 30 tick | continuity_v2 | `backend/agents/consistency_guardian.py` |
| 9 | NoveltyCritic | 每 20 tick | small | `backend/agents/novelty_critic.py` |

### 多 LLM 提供商

`core/config.py` 使用数据驱动 provider catalog。运行时配置优先级固定为：请求显式配置 →
Stage 显式配置 → 服务端持久配置 → 环境 fallback；浏览器还可使用会话或当前设备配置。

`backend/config/settings.py` 用 `importlib` 加载 `core/config.py:get_active_llm_config()`,
兼容读取部署环境和根 `config.json`。真实验收只显式只读传入原始 `coding.txt`，不把凭据
复制进仓库文件。

### 数据存储

`backend/data/novels/{novel_id}/` 下，默认 Author 主要维护 `production_spec.json`、
`book_outline.json`、`style_profiles.json`、`active_style.json`、`generation_jobs/`、
`production_attempts/`、`production_events/`、`production_chapters/` 及 StoryBible/Canon/
Thread/Memory/transaction 权威文件。

实验性 simulation 继续维护：
- `tick_state.json` — Pydantic v2 dump(WorldState + CharacterProfile×N + OpenLoop + …)
- `summary_tree.json` — 分层摘要 + L3 传说
- `ticks.db` — SQLite WAL (tick_log + events 两表)
- `knowledge_graph.json` + `snapshots/` — NetworkX 图 + 每 50 tick 快照
- `chroma_db/` — 向量索引
- `narratives/tick_NNNNNN.txt` — Narrator 产出

## Commands

### 开发循环

```bash
# 安装依赖
pip install -r requirements-dev.txt
cd frontend && npm install && cd ..

# 一键启动前后端
start.bat                    # Windows
./start.sh                   # macOS/Linux

# 单独启动
python run.py --reload                            # 后端 → http://127.0.0.1:8762
cd frontend && npm run dev                        # 前端 → http://127.0.0.1:3143/

# 冷启动一个新世界
python -m backend.bootstrap_prompts --novel-id mountain --seed "..."

# 推进 tick
curl -X POST http://127.0.0.1:8762/api/tick/run
```

### 测试

```bash
# 全部测试
python -m pytest backend/tests/ -v

# 单文件
python -m pytest backend/tests/test_orchestrator_p0.py -v

# 单用例
python -m pytest backend/tests/test_orchestrator_p0.py::test_name -v

# 覆盖率
python -m pytest backend/tests/ --cov=backend --cov-report=term-missing
```

测试用 `conftest.py` 的 `mock_llm` fixture 替换 `nf_core.llm_client.llm_client.chat`,
不依赖真实 LLM。

### 生产构建

```bash
cd frontend && npm run build      # 产物 → frontend/dist/
python run.py                     # FastAPI 自动 mount frontend/dist 到 /nw/
```

## 关键路径

| 文件 | 作用 |
|------|------|
| `backend/main.py` | FastAPI 入口 + 静态资源 mount + lifecycle 钩子 |
| `backend/tick_runtime.py` | Orchestrator + TickState + TickDB 单例容器 |
| `backend/bootstrap_prompts.py` | 5 prompt 冷启动 CLI |
| `backend/api/tick_routes.py` | 14 条 tick 控制 REST 端点 |
| `backend/api/routes.py` | 节级管线 REST + SSE(legacy 节级管线) |
| `backend/config/settings.py` | 服务端配置与 legacy 环境/config fallback |
| `backend/nf_core/llm_client.py` | OpenAI SDK 包装,支持 streaming + JSON mode |
| `backend/nf_core/action_resolver.py` | 纯 Python 行动冲突解析 |
| `backend/nf_core/prompt_builder.py` | Token 自适应裁剪 |
| `core/config.py` | 多 provider 路由,backend 通过 importlib 加载 |
| `memory_system/models.py` | Pydantic v2 tick 契约 + 遗留 dataclass |
| `evaluation/continuity_v2.py` | ConsistencyGuardian 复用的连贯性评估器 |
| `frontend/vite.config.js` | base 默认 `/`，`/api` → 8762 proxy（host 强制 IPv4） |
| `frontend/src/` | React 18 + react-force-graph-2d + react-markdown |
| `run.py` | 根级启动入口,等价 uvicorn backend.main:app --app-dir backend |

## 路径常量约定

- backend 内大多数模块通过 `sys.path.insert` 把 `backend/` 和项目根加入路径,
  然后用裸 import:`from agents.X`, `from memory.tick_state`, `from memory_system.models`
- 入口脚本 (main.py / bootstrap_prompts.py / tests/conftest.py) 负责设置 sys.path
- 不要在 backend 子模块里写 `from backend.X` —— 保持原有的裸 import 风格

## 重要模式

### Pydantic v2 契约
所有 tick 数据契约在 `memory_system/models.py`,带 `model_dump_json()` / `model_validate_json()`,
FastAPI 直接消费,SQLite 序列化与 SSE 推送都靠它。

### 原子写
TickState / SummaryTree 都用 `tempfile.mkstemp + os.replace` 原子写,
防止崩溃留下半截文件。

### 路径安全
backend 内所有文件操作通过 `TickState.data_dir` 走绝对路径,不接受用户输入路径拼接。

### Narrator 沉默
事件总价值 < 5 时 Narrator 跳过 — 这是 feature,不是 bug。
长期沉默通过 `inject-event` API 或 `OpenLoop ≥ 3` 触发。

## 测试约定

测试文件为 `backend/tests/test_*.py`；不要在文档中缓存易过期的文件/用例总数。

- 用 `mock_llm` fixture 控制 LLM 输出
- `mock_llm.set_responses([dict, str, ...])` 排队下一组返回
- 不依赖真实 LLM 调用,测试 2.8 秒全过
- pytest 配置:根级无 `pytest.ini`,直接 `python -m pytest backend/tests/`

## 不要

- ❌ 重新引入 `core.NovelGenerator` 链路(章节式生成)— 已归档到 `old/core/`
- ❌ 在 backend 子模块写 `from backend.X` — 用裸 import 即可
- ❌ 改动 `old/` 内容 — 那是只读归档
- ❌ 在 `config.json`、作品目录或仓库文件中硬编码 API key。浏览器使用会话/设备配置，
  服务端由部署环境或秘密管理系统注入；真实验收只显式只读传入原始 `coding.txt`
