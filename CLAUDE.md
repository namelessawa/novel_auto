# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

无限小说生成系统 (Infinite Novel Generation System) - An AI-powered novel generation system using DeepSeek API with a four-layer memory mechanism for coherent, continuous story generation.

## Core Architecture

### Active Memory System (wired into `NovelGenerator`)

The running pipeline maintains story coherence through these modules in `memory_system/`, all of which `core/generator.py` imports and updates:

1. **Sliding Window (`sliding_window.py`)** - Short-term memory retaining recent text, measured by **tokens** (`SLIDING_WINDOW_MAX_TOKENS`, default 2500) via `utils/token_counter.py`. The `max_chars` parameter is kept only for backward compatibility.
2. **Entity State Tracker (`entity_state.py`)** - Global state machine tracking characters, locations, and world rules with per-chapter snapshots
3. **Hierarchical Summarizer (`hierarchical_summary.py`)** - Three-level summaries: high-level outline, mid-level story arcs, low-level chapter summaries
4. **Long-Term Memory (`long_term_memory.py`)** - RAG-based vector storage using ChromaDB for semantic retrieval of historical events
5. **Character Relationship Graph (`character_relationship.py`)** - Tracks inter-character relationships
6. **Knowledge Graph (`knowledge_graph.py`)** - **新增 (阶段三)** NetworkX 有向图，实体/关系建模 + 快照回滚。可通过 `NovelGenerator(enable_knowledge_graph=True)` 启用（默认开启）。与 `character_relationship.py` 并行存在。共享 `memory_system/models.py` 的 dataclass。

> **There is a second, parallel memory architecture that is NOT yet wired in** — see "Built-but-unintegrated modules" below before assuming a module is live.

### Multi-Provider LLM Configuration

`core/config.py` 现支持多 LLM 提供商（通过 `LLM_PROVIDER` 环境变量切换）：
- `deepseek` (默认): `DEEPSEEK_*` 环境变量
- `mimo` (小米): `MIMO_*` 环境变量，base_url 默认 `https://token-plan-cn.xiaomimimo.com/v1`
- `custom`: `CUSTOM_*` 环境变量，任意 OpenAI 兼容端点

运行时调用 `core.config.get_active_llm_config()` 获取 `{provider, label, api_key, base_url, model, max_tokens, temperature, timeout}`。`NovelGenerator` 自动使用 active provider；Express `/api/config` 与前端 UI 提供切换控件。

### Multi-Novel Project Management

`core/novel_manager.py` 维护 `results/manifest.json`，跟踪每本小说的 `id / title / created_at / updated_at`。已有 `results/{topic}/` 目录会自动 backfill 到 manifest。前端 Express `/api/novels` GET / POST / PUT / DELETE 暴露管理能力。

### Parallel FastAPI Agent Backend (`agent_backend/`)

阶段四并行接入：`agent_backend/` 是一个薄壳启动器，通过 subprocess 启动 `novel_frame/backend/main.py` (FastAPI + SSE)，提供 Agent-style 多智能体生成管线（outline → retrieval → validation → writer → update）。

- 启动: `python -m agent_backend --port 8000`
- LLM 配置: 通过 `novel_frame/backend/config/settings.py` 的桥接逻辑读取主项目 `.env` 的 active provider；切换提供商无需重启
- 数据目录: `novel_frame/backend/data/novels/{novel_id}/` (与主项目 `results/` 并存)
- 与主项目 CLI/Express 后端**并行**运行，互不干扰

### Key Components

The runtime engine lives under `core/` (a single Python package that `core/__init__.py` re-exports). Only the four entry-point scripts (`main.py`, `create_novel.py`, `continue_novel.py`, `validate_system.py`) remain at the project root.

- **`core/generator.py`** - Main `NovelGenerator` class orchestrating all modules. Import as `from core import NovelGenerator`.
- **`core/llm_client.py`** - OpenAI SDK wrapper supporting DeepSeek API with streaming and JSON mode
- **`core/chapter_analyzer.py`** - LLM-based extraction of characters, relationships, events from chapters
- **`core/background_task.py`** - Threading-based async post-processing for memory updates
- **`core/embedding_service.py`** - Sentence Transformers for vector embeddings (BAAI/bge-small-zh-v1.5)
- **`core/config.py`** - Centralized configuration loaded from environment variables (`from core.config import ...`)
- **`evaluation/continuity_v2.py`** - `EnhancedContinuityEvaluator`, the **active** multi-dimensional continuity scorer used by `NovelGenerator`. (The legacy `continuity_evaluator.py` has been deleted.)
- **`main.py`** - Interactive menu entry point dispatching to `create_novel.py` / `continue_novel.py`

### Data Flow

```
User Input → NovelGenerator.generate_next_chapter()
    → _build_full_prompt() (aggregates all memory contexts)
    → LLMClient.generate() → Chapter Content
    → EnhancedContinuityEvaluator.evaluate() (multi-dimensional; if prev chapter exists)
    → Optimize via generate_fix_prompt() if score < CONTINUITY_THRESHOLD
    → Save chapter → ChapterAnalyzer.analyze()
    → apply_analysis_to_memory() → Update all memory modules
```

### Built-but-unintegrated modules (IMPORTANT)

Several subsystems exist in the tree but are **not imported by `core/generator.py` or the runtime pipeline**. They have been quarantined under `experimental/`. Treat them as in-progress scaffolding, not live behavior. Verify with `grep` before assuming any is active:

- **`experimental/memory_system/`** — cognitive-science four-layer memory: `unified_memory.py` (`UnifiedMemorySystem`) plus `working_memory.py`, `episodic_memory.py`, `semantic_memory.py`, `procedural_memory.py`. Intended to eventually replace the five active modules under `memory_system/`, but only wired to itself.
- **`experimental/core/`** — `event_bus.py`, `llm_scheduler.py`, `plugin_manager.py` (event-driven plugin architecture / multi-LLM scheduling). Note: distinct from the live `core/` package at the project root.
- **`experimental/plot_engine/`** — `foreshadowing.py`, `story_arc.py` (foreshadowing lifecycle and multi-thread arc management).
- **`experimental/evaluation/`** — `context_integrity.py` and `refinement.py`. Only `evaluation/continuity_v2.py` (live) is wired in.

See `experimental/README.md` for the quarantine rationale and the steps required to integrate any of these modules. `IMPLEMENTATION_PLAN.md`, `PROGRESS_SUMMARY.md`, and `REFACTORING_REPORT.md` track the original migration plan.

## Commands

### Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Configure API keys (create .env file)
cp .env.example .env
# Edit .env with DEEPSEEK_API_KEY and optionally DASHSCOPE_API_KEY
```

### Running
```bash
# Terminal mode - create new novel
python create_novel.py

# Terminal mode - continue existing novel
python continue_novel.py

# Frontend mode (Express + ejs，主项目原前端)
cd frontend && npm install && npm start
# Access at http://localhost:8080

# Agent backend (FastAPI + SSE，阶段四并行接入)
python -m agent_backend --port 8000
# 然后访问 novel_frame 自带的 Vite/React 前端 (cd novel_frame/frontend && npm i && npm run dev)
# 或直接调用 REST/SSE API：http://localhost:8000/api/...
```

### Testing
A `pytest` suite lives in `tests/` (fixtures in `tests/conftest.py`; unit tests under `tests/unit/`, with memory tests in `tests/unit/memory/`). `tests/integration/` exists but is currently empty. There is no `pytest.ini`/`pyproject.toml` config — pass paths explicitly.

```bash
# Run all unit tests
python -m pytest tests/unit/ -v

# Run with coverage report
python -m pytest tests/unit/ --cov=. --cov-report=term-missing

# Run a single test file / single test
python -m pytest tests/unit/test_token_counter.py -v
python -m pytest tests/unit/test_token_counter.py::test_name -v
```

Coverage is currently concentrated in the leaf utilities/evaluators (`token_counter`, `sliding_window`, `continuity_v2`, `embedding_service`); `core/llm_client.py` and `core/generator.py` are largely untested because they require live LLM calls — mock the LLM when adding tests for them. The frontend `npm test` script is a placeholder no-op.

## Configuration

All configuration is centralized in `core/config.py`. Key settings loaded from environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | 当前生效提供商 (`deepseek` / `mimo` / `custom`) | `deepseek` |
| `LLM_MAX_TOKENS` | 共享 max_tokens | `8192` |
| `LLM_TEMPERATURE` | 共享 temperature | `0.7` |
| `LLM_TIMEOUT` | 共享 API 超时秒数 | `120` |
| `DEEPSEEK_API_KEY` | DeepSeek API key | - |
| `DEEPSEEK_BASE_URL` | DeepSeek endpoint | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | DeepSeek model name | `deepseek-chat` |
| `MIMO_API_KEY` | MiMo (小米) API key | - |
| `MIMO_BASE_URL` | MiMo endpoint | `https://token-plan-cn.xiaomimimo.com/v1` |
| `MIMO_MODEL` | MiMo model name | `mimo-chat` |
| `CUSTOM_API_KEY` | 自定义提供商 API key | - |
| `CUSTOM_BASE_URL` | 自定义提供商 endpoint | - |
| `CUSTOM_MODEL` | 自定义提供商 model | - |
| `DASHSCOPE_API_KEY` | DashScope API key (for images) | - |
| `ENABLE_MULTIMEDIA` | Enable TTS/image/video generation | `false` |
| `SLIDING_WINDOW_MAX_TOKENS` | Short-term memory size | `2500` |
| `CONTINUITY_THRESHOLD` | Chapter continuity score threshold | `80.0` |

## Frontend

Express.js server in `frontend/server.js` provides:
- Web UI at `/` for creating/continuing novels
- REST API endpoints for topics, chapters, memory system data
- Process management for Python generation tasks
- Multimedia file serving

The frontend communicates with Python scripts via environment variables (`NOVEL_TOPIC`, `NOVEL_CUSTOM_PROMPT`).

## Important Patterns

### Memory Module Interface
Each memory module follows a consistent pattern:
- `__init__(memory_dir: str)` - Initialize with storage directory
- `load_from_disk()` / `save_to_disk()` - Persistence
- `to_text_description()` - Format for LLM prompts
- `clear()` - Reset state

### Token-Aware Prompt Building
`_build_full_prompt()` in `core/generator.py` implements adaptive token reduction:
- Priority order for reduction: RAG → Sliding Window → Hierarchy → Entities
- Monitors token count via `tiktoken`
- Iteratively reduces context if exceeding 6000 token threshold

### Path Safety
All file operations validate paths stay within project directory:
```python
def _safe_path(self, path: str) -> str:
    project_root = Path(__file__).parent.resolve()
    safe = Path(path).resolve()
    if not str(safe).startswith(str(project_root)):
        raise ValueError(f"Unsafe path: {path}")
    return str(safe)
```

## Output Structure

```
results/
└── {topic_name}/
    ├── chapter_001_第一章.txt
    ├── chapter_002_第二章.txt
    ├── sliding_window.json
    ├── entity_state.json
    ├── entity_snapshots/
    │   ├── chapter_001.json
    │   └── chapter_002.json
    ├── hierarchical_summary.json
    ├── long_term_events.json
    ├── long_term_memory_db/  (ChromaDB)
    ├── character_relationships.json
    └── multimedia/
        └── chapter_001/
            ├── audio/
            ├── images/
            └── video/
```
