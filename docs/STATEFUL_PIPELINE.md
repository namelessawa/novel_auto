# Stateful Generation Pipeline Architecture

## Overview

The stateful generation pipeline (v2.50+) extends the Author production system with a
multi-LLM chapter generation flow that maintains deterministic state, supports
user confirmation gates, and provides idempotent recovery.

```
创建小说
   ↓
生成第1、2章梗概 (Synopsis LLM)
   ↓
用户编辑梗概
   ↓
用户确认生成章节
   ↓
[第3章开始：传递 LLM]
   ↓
小说 LLM (Novel Writer)
   ↓
伏笔 LLM (Foreshadow Extractor)
   ↓
信息 LLM (Information Extractor)
   ↓
整合 LLM (Integration)
   ↓
ChromaDB
   ↓
进入下一章
   ↓
再次等待用户确认
   ↓
循环
```

## Core Principles

1. **Programs handle deterministic rules**: All probability logic, state machines,
   and random decisions are implemented in Python. LLMs never modify state.

2. **LLMs handle semantic work**: Writing, extraction, summarization, and context
   compilation are LLM responsibilities.

3. **CanonicalState remains authoritative**: ChromaDB is derived/retrieval storage.
   It can be rebuilt from committed data.

4. **Idempotent recovery**: All random decisions are persisted in receipts. Retry
   replays the same decisions without re-rolling.

## Key Components

### Domain Models (`backend/story/stateful_pipeline/models.py`)

| Model | Purpose |
|-------|---------|
| `ChapterSynopsis` | User-editable synopsis per chapter with revision tracking |
| `InformationSchema` | Configurable fields for information extraction |
| `ForeshadowRecord` | Individual foreshadow with probability and eligibility |
| `ForeshadowSelectionState` | Global streak and discard unlock state |
| `ForeshadowSelectionReceipt` | Persisted random decisions for idempotent replay |
| `ChapterGenerationPreference` | User choices before generation |
| `TransferContext` | Output of Transfer LLM |
| `ChapterPipelineState` | Current pipeline phase and bindings |

### Foreshadow Selection Service

Pure deterministic algorithm implementing:

- **10-chapter minimum age**: Foreshadows become eligible 10 chapters after creation
- **2% base probability**: Starting probability for eligible foreshadows
- **+2% per miss**: Probability increases when participating but not selected
- **1/n collision resolution**: Multiple hits → uniform random selection
- **3-chapter cooldown**: Collision losers skip 3 chapters, probability frozen
- **25% discard**: Only after 3-consecutive-selections unlock
- **Persisted receipts**: All decisions saved for recovery

### ChromaDB Repository

- Idempotent document IDs: `{novel_id}:{chapter}:{schema_revision}:{field}:{index}`
- Per-novel isolation via metadata filter
- Upsert semantics (retry-safe)
- Rebuild capability from committed chapter information

### Pipeline Phases

```
awaiting_user_confirmation → preparing_context → writing →
extracting_foreshadows → extracting_information → integrating_memory →
committing → chapter_completed
```

## API Endpoints

### Synopsis
- `GET /api/novels/{id}/pipeline/synopsis` - List all synopses
- `GET /api/novels/{id}/pipeline/synopsis/{chapter}` - Get specific synopsis
- `PUT /api/novels/{id}/pipeline/synopsis/{chapter}` - Update synopsis
- `POST /api/novels/{id}/pipeline/synopsis/generate` - Auto-generate synopses

### Information Schema
- `GET /api/novels/{id}/pipeline/schema` - Get current schema
- `PUT /api/novels/{id}/pipeline/schema` - Update schema fields
- `POST /api/novels/{id}/pipeline/schema/generate` - Auto-generate schema

### Foreshadows
- `GET /api/novels/{id}/pipeline/foreshadows` - List foreshadows
- `GET /api/novels/{id}/pipeline/foreshadows/state` - Selection state
- `GET /api/novels/{id}/pipeline/foreshadows/receipt/{chapter}` - Selection receipt

### Pipeline Control
- `GET /api/novels/{id}/pipeline/status/{chapter}` - Chapter pipeline status
- `POST /api/novels/{id}/pipeline/confirm` - Confirm chapter for generation
- `POST /api/novels/{id}/pipeline/generate/{chapter}` - Start generation

### ChromaDB
- `GET /api/novels/{id}/pipeline/chroma/status` - Document count
- `POST /api/novels/{id}/pipeline/chroma/rebuild` - Rebuild from source

## Data Storage

All pipeline data is stored in `{novel_data_dir}/pipeline/`:

```
pipeline/
├── synopsis_ch1.json
├── synopsis_ch2.json
├── information_schema.json
├── foreshadows.json
├── foreshadow_state.json
├── foreshadow_receipt_ch15.json
├── transfer_ch3.json
├── pipeline_state_ch3.json
├── information/
│   └── chapter_1.json
└── integration/
    └── integration_ch1.json
```

## Migration from Existing Novels

Novels created before v2.50 will:
- Have no synopses (auto-generated on first pipeline use)
- Have no information schema (auto-generated based on story context)
- Have no foreshadows (empty state)
- Have no ChromaDB collection (created on first integration)

The system provides safe defaults and does not require data migration.
All persistence stores return `None` or empty defaults when data is missing.

## Integration with Existing System

### Novel Writer Integration
- `_write_chapter()` delegates to `AuthorGenerationService.run()` with a `SectionGoal`
- Style prefix applied via `AuthorWriter(style_prompt_prefix=...)` constructor
- Existing validation, repair, and transaction machinery fully reused
- Only the Novel LLM receives the style prefix; foreshadow/info/integration LLMs do not

### StyleProfile Extension
- Added `writer_prompt_prefix: str` field to `StyleProfile`
- Included in `prompt_contract()` and thus participates in `prompt_hash`
- Style changes create new revision; only affect next unstarted chapter
- Frozen at confirmation via `ActiveStyleBinding.profile_revision`

### TaskManager Integration
- New task kind: `pipeline_chapter_generation`
- `POST /pipeline/generate/{chapter}` submits async task
- Progress streamed via SSE at `/api/tasks/{task_id}/stream`
- One active task per novel enforced by TaskManager

## Frontend

The PipelineView (`frontend/src/dashboard/views/PipelineView.jsx`) provides:
- Synopsis editor with revision tracking
- Information schema field configuration
- Foreshadow status table with probability display
- Chapter confirmation UI with foreshadow mode selection
- Pipeline phase progress display
- SSE progress subscription via existing task stream

## Testing

Key test files:
- `backend/tests/test_foreshadow_selection.py` - 32 tests for probability rules
- `backend/tests/test_pipeline_persistence.py` - 21 tests for storage and ChromaDB

Run tests:
```bash
python -m pytest backend/tests/test_foreshadow_selection.py -v
python -m pytest backend/tests/test_pipeline_persistence.py -v
```

All existing tests continue to pass:
- `backend/tests/test_author_generation_service.py` - 20 passed
- `backend/tests/test_production_models.py` - 5 passed
- `frontend` - 28 passed, build successful
