# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

无限小说生成系统 — 单栈 FastAPI + React/Vite,9 Agent + 7 阶段 Tick 调度的
多智能体小说生成系统。设计哲学来自
[`infinite-novel-multiagent-prompts.md`](./infinite-novel-multiagent-prompts.md):
**故事是模拟的副产品,Narrator 选择性讲述**。

> v1.x 章节驱动单体生成器已整体归档到 `old/`,不参与运行时。详见 `CHANGELOG.md` 2.1.0。

## 核心架构

### 9 Agent + 7 阶段 Tick 循环

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

`core/config.py` 通过 `LLM_PROVIDER` 环境变量切换:
- `deepseek` (默认), `mimo` (小米), `custom` (任意 OpenAI 兼容)

`backend/config/settings.py` 用 `importlib` 加载 `core/config.py:get_active_llm_config()`,
读取 `.env`。`.env` 缺失时回落到根 `config.json`。

### 数据存储

`backend/data/novels/{novel_id}/` 下:
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
python run.py                     # FastAPI 把 frontend/dist 挂到根路径 /
```

## 关键路径

| 文件 | 作用 |
|------|------|
| `backend/main.py` | FastAPI 入口 + 静态资源 mount + lifecycle 钩子 |
| `backend/tick_runtime.py` | Orchestrator + TickState + TickDB 单例容器 |
| `backend/bootstrap_prompts.py` | 5 prompt 冷启动 CLI |
| `backend/api/tick_routes.py` | 14 条 tick 控制 REST 端点 |
| `backend/api/routes.py` | 节级管线 REST + SSE(legacy 节级管线) |
| `backend/api/multimodal_routes.py` | v2.33 多模态: 分段 + 图 + TTS + 视频 (复用 task_manager SSE) |
| `backend/nf_core/text_segmenter.py` | 中文分段, 按句/逗号切, 段长 15-60 字 |
| `backend/nf_core/edge_tts_client.py` | edge-tts wrapper, 文本 → mp3, WordBoundary 拿时长 |
| `backend/nf_core/video_composer.py` | imageio-ffmpeg + libx264 把图/音频/字幕拼成 mp4 |
| `backend/multimedia/asset_store.py` | per-novel-per-section 资产: manifest.json + img/audio/mp4 |
| `backend/config/settings.py` | `.env` + `config.json` 双源配置 |
| `backend/nf_core/llm_client.py` | OpenAI SDK 包装,支持 streaming + JSON mode |
| `backend/nf_core/action_resolver.py` | 纯 Python 行动冲突解析 |
| `backend/nf_core/prompt_builder.py` | Token 自适应裁剪 |
| `core/config.py` | 多 provider 路由,backend 通过 importlib 加载 |
| `memory_system/models.py` | Pydantic v2 tick 契约 + 遗留 dataclass |
| `evaluation/continuity_v2.py` | ConsistencyGuardian 复用的连贯性评估器 |
| `frontend/vite.config.js` | base=/(可通过 VITE_BASE_PATH 改),/api → 8762 proxy(host=127.0.0.1 强制 IPv4) |
| `frontend/src/` | React 18 + react-force-graph-2d + react-markdown |
| `run.py` | 根级启动入口,等价 uvicorn backend.main:app --app-dir backend |

## Token 预算调参 env vars (v2.38 cost-quality-loop)

生产环境可通过以下 env 覆盖 v2.38 默认值:

| env var                       | default | 用途                                         |
| ----------------------------- | ------: | -------------------------------------------- |
| `CRITIC_MIN_NARRATIVE_LEN`    | 600     | < 此阈值的 narrative 跳过 critic 整段        |
| `CRITIC_IMPORTANCE_MIN`       | 7       | tick max(narrative_value) < 此阈值跳 critic. Phase 2 Stage 2 重要性门控. 0 = critic 总跑 (老 v15); 999 = 总跳 (v16) |
| `CRITIC_MAX_TOTAL_ROUNDS`     | 1       | critic 修订总轮次上限 (critique + modify)    |
| `CRITIC_MAX_REVISE_ROUNDS`    | 1       | revise 单类型上限                            |
| `CRITIC_MAX_REWRITE_ROUNDS`   | 1       | rewrite 单类型上限                           |
| `CRITIC_CRITIQUE_MAX_TOKENS`  | 1500    | critic critique LLM 输出 budget              |
| `CRITIC_REVISE_MAX_TOKENS`    | 4096    | critic revise/rewrite LLM 输出 budget        |
| `CRITIC_ENABLE_LLM`           | 1       | 0 关闭 critic LLM, 仅 det-only               |
| `CRITIC_FORCE_LLM`            | 0       | 1 强制 LLM critique (即使 det 已 high)       |
| `CHARACTER_AGENT_CONCURRENCY` | 6       | batch_decide 并发数                          |
| `NARRATOR_STRONG_MODEL_TICKS` | 100     | 前 N tick 用最强模型建立风格基准             |
| `NARRATOR_ENABLE_CRITIC`      | (auto)  | 1=强制 / 0=关 / 空 = 测试关 / 生产开         |
| `LLM_MAX_TOKENS_CAP`          | 65536   | LLMClient.chat 顶层 max_tokens 硬上限        |
| `LLM_TIMEOUT`                 | 600     | LLM 调用超时 (秒). DEEPSEEK_TIMEOUT 为旧别名 |

## Phase 2 Quality-First Loop 参数 (iter#76+)

> Phase 1 (cost) 已饱和, Phase 2 切到 quality + cost 联合优化.
> 参数固化以下默认; 修改前必须在 ITERATION_LOG.md 写明原因.

| 参数                          | 默认值                         | 说明                                         |
| ----------------------------- | :----------------------------- | -------------------------------------------- |
| `JUDGE_MODEL`                 | `mimo-v2.5-pro` (跨家族评判)   | 用 .env `MIMO_*` 凭据. self-bias 风险最低     |
| `JUDGE_BUDGET_PER_BENCH`      | 50,000 tokens                  | 单次 quality bench judge 总预算上限           |
| `JUDGE_PAIRWISE_DENSITY`      | 每 30 tick 抽 10 对            | 关键节拍 (arc / high severity) 优先入样      |
| `BENCH_FIXED_SEEDS`           | 3 个固定 seed                  | 写入 `scripts/bench_tick.py` 默认; 跨 bench 可复现 |
| `QUALITY_DET_ALWAYS`          | true                           | 确定性指标层每次 bench 必跑 (零成本)         |
| `QUALITY_JUDGE_PROMPT_VER`    | (随 prompt 入库自动赋值)        | judge prompt 版本号, 写入产物 metadata       |


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

测试文件:`backend/tests/test_*.py`,67 个文件 574 个用例 (v2.37)。

- 用 `mock_llm` fixture 控制 LLM 输出
- `mock_llm.set_responses([dict, str, ...])` 排队下一组返回
- 不依赖真实 LLM 调用,全量 ~32 秒跑完
- pytest 配置:根级无 `pytest.ini`,直接 `python -m pytest backend/tests/`

## 不要

- ❌ 重新引入 `core.NovelGenerator` 链路(章节式生成)— 已归档到 `old/core/`
- ❌ 在 backend 子模块写 `from backend.X` — 用裸 import 即可
- ❌ 改动 `old/` 内容 — 那是只读归档
- ❌ 在 `config.json` 里硬编码 API key — 放 `.env`
