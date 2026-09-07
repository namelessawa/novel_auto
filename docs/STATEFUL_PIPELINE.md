# Stateful Generation Pipeline Architecture

## Overview

The stateful generation pipeline (v2.50+, converged in the P0 architecture
refactor) is an **orchestration layer on top of Author production**. It owns
confirmation gates, chapter sequencing, deterministic foreshadow selection and
derived retrieval. It does **not** own a second novel-writing engine.

```
StoryBible + BookOutline + CanonicalState + StoryThreadRepository
        ↓
Stateful Pipeline
  · user confirmation (immutable authority freeze)
  · chapter goal resolution (frozen synopsis + BookOutline anchor)
  · deterministic foreshadow selection (persisted receipt)
        ↓
AuthorGenerationService          ← the only official generation chain
  ChapterPlan → NarrativeContract → ContextBuilder → Writer
  → NarrativeContractValidator → StoryValidator → at most one Repair
  → atomic transaction commit
        ↓
CanonicalState + StoryThreads + MemoryRepository + committed TickSection
        ↓
Pipeline derived work over the *committed* prose
  foreshadow extraction → information extraction → ChromaDB integration
        ↓
Pipeline verifies the Author commit → COMPLETED
        ↓
Next chapter waits for a new confirmation
```

**The pipeline itself has no second official Writer.** Official prose is
generated, validated, repaired and committed by Author production, and
`COMPLETED` only holds after that commit was verified.

## Core Principles

1. **One fact source, one Writer, one Validator, one commit boundary.**
   `CanonicalState` is the only current-fact authority, `StoryThreadRepository`
   the only story-obligation authority, and the Author transaction the only
   commit boundary. The pipeline never writes any of them.

2. **Programs handle deterministic rules**: probability logic, state machines
   and random decisions are Python. LLMs never mutate state.

3. **LLMs handle semantic work**: writing, extraction, summarization.

4. **ChromaDB is derived retrieval only.** It can be rebuilt from committed
   chapter information and is never an authority.

5. **Pipeline phase is orchestration state only.** It is not evidence that
   anything was committed; the recorded Author commit evidence is.

6. **Idempotent recovery**: random decisions are persisted in receipts and the
   Author transaction id is deterministic per attempt, so a replay never
   re-rolls and never pays for a second Writer call.

## Key Components

### Author Bridge (`backend/story/stateful_pipeline/author_bridge.py`)

The only place that converts a confirmed chapter into Author production input.

| Symbol | Purpose |
|--------|---------|
| `resolve_chapter_intent()` | BookOutline objective + frozen synopsis (+ selected foreshadow) → one chapter goal. Refuses when no anchor exists. |
| `build_section_goal()` | `ChapterIntent` → `SectionGoal` with production ordinals and the outline's `required_events` / `required_end_states` / `prohibited_additions` as `NarrativeContractInput`. |
| `author_request_id()` | Deterministic transaction id per `(novel, chapter, attempt)`; replay returns the committed transaction instead of writing again. |
| `verify_author_commit()` | Fails closed unless the transaction committed, official prose exists, CanonicalState advanced, and both validators accepted. |

### Domain Models (`backend/story/stateful_pipeline/models.py`)

| Model | Purpose |
|-------|---------|
| `ChapterSynopsis` | User-editable synopsis per chapter with revision tracking |
| `AuthorityRevisions` | The eight revisions frozen at confirmation, plus `drift()` |
| `ChapterConfirmation` | Immutable confirmation binding, including the frozen synopsis **content** |
| `ChapterPipelineState` | Phase, attempt counter, frozen snapshot and Author commit evidence |
| `InformationSchema` | Configurable fields for derived information extraction |
| `ForeshadowRecord` / `ForeshadowSelectionState` / `ForeshadowSelectionReceipt` | Deterministic foreshadow lifecycle and replayable random decisions |
| `ChapterGenerationPreference` | User choices frozen at confirmation |
| `TransferContext` | Derived retrieval artifact (experimental; not on the official path) |

### StoryBible → PromptView (`llm_roles.py`)

`story_bible_prompt_view()` + `render_story_bible_prompt()` are the single,
strongly typed projection used by pipeline-owned prompts (synopsis, schema).
Every field is read by name, so renaming a `StoryBible` field fails loudly
instead of silently dropping setting material. There is no `hasattr`-based
degradation anywhere in the pipeline.

The **Writer** does not use this projection: it receives the full StoryBible
slot from the Author `ContextBuilder`, which renders `premise`,
`setting_summary`, `immutable_world_rules`, `forbidden_deviations`,
`protagonist_contracts`, `main_conflicts` and `ending_direction`.

### Foreshadow Selection Service

Pure deterministic algorithm:

- **8-chapter minimum age** before a foreshadow becomes eligible
- **2% base probability**, **+2% per miss**
- **1/n collision resolution** for simultaneous hits
- **3-chapter cooldown** for collision losers, probability frozen
- **25% discard**, only after 3 consecutive selections unlock it
- **Persisted receipts** so retry replays the same decisions

The selected foreshadow reaches the official Writer as an explicit directive
appended to the chapter objective — not through a second context mechanism.

### ChromaDB Repository

- Idempotent document IDs: `{novel_id}:{chapter}:{schema_revision}:{field}:{index}`
- Per-novel isolation via metadata filter
- Upsert semantics (retry-safe)
- Rebuild capability from committed chapter information

### Pipeline Phases

```
awaiting_user_confirmation
        ↓ confirm
confirmed
        ↓ generate
preparing_context → writing → extracting_foreshadows →
extracting_information → integrating_memory → committing
        ↓                                            ↓
chapter_completed                                  failed
```

- `confirm` produces `confirmed` and freezes every authority revision plus the
  synopsis text itself.
- `generate` is only allowed from `confirmed`, or when resuming an in-flight
  attempt / replaying a `chapter_completed` one.
- `writing` delegates to `AuthorGenerationService.run()`, which performs the
  Author commit. `committing` then re-reads the transaction, the official
  `TickSection`, `CanonicalState`, `StoryThreadRepository` and
  `MemoryRepository` from disk. Only if all of it verifies does the chapter
  become `chapter_completed`; otherwise it becomes `failed`.
- `failed` never auto-reruns. An explicit `retry` creates attempt N+1 with a
  new Author transaction id and purges the chapter's derived artifacts first,
  so new prose can never be paired with a previous attempt's information or
  memory.
- Re-entering a `chapter_completed` chapter is a pure read: zero Writer calls,
  zero extraction calls, zero authority mutation.

### Revision freeze

Confirmation records `synopsis_revision`, `story_bible_revision`,
`canon_revision`, `story_thread_revision`, `memory_revision`,
`outline_revision`, `style_revision` and `information_schema_revision`, plus
the synopsis title/text. Before the Author chain is invoked, all eight are
re-checked against the live authorities. Any drift raises
`ConfirmationStaleError` (HTTP 409) and the chapter must be confirmed again —
generation never silently binds to the newer revision.

## API Endpoints

### Synopsis
- `GET /api/novels/{id}/pipeline/synopsis` - List all synopses
- `GET /api/novels/{id}/pipeline/synopsis/{chapter}` - Get specific synopsis
- `PUT /api/novels/{id}/pipeline/synopsis/{chapter}` - Update synopsis (new revision)
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
- `GET /api/novels/{id}/pipeline/status` - Current chapter
- `GET /api/novels/{id}/pipeline/status/{chapter}` - Phase, attempt and verified commit evidence
- `POST /api/novels/{id}/pipeline/confirm` - Freeze authorities → `confirmed`
- `POST /api/novels/{id}/pipeline/generate/{chapter}` - Generate; 409 unless confirmed
- `POST /api/novels/{id}/pipeline/retry/{chapter}` - New attempt for a failed/completed chapter

`generate` returns one of:

| Response | Meaning |
|---|---|
| `409` | Not confirmed, confirmation stale, or the previous attempt failed |
| `{"status": "queued", "committed": false, ...}` | Task accepted; nothing committed yet |
| `{"status": "already_completed", "committed": true, ...}` | Replay of a verified commit |
| `{"status": "already_completed", "committed": false, ...}` | A `chapter_completed` record whose manuscript is missing — fails closed |

`committed` is always derived from recorded Author commit evidence
(`transaction_id`, `section_id`, `char_count`, `canonical_revision`), never
from the phase name alone.

### ChromaDB
- `GET /api/novels/{id}/pipeline/chroma/status` - Document count
- `POST /api/novels/{id}/pipeline/chroma/rebuild` - Rebuild from source

## Data Storage

Pipeline-owned derived data lives in `{novel_data_dir}/pipeline/`:

```
pipeline/
├── synopsis_ch1.json
├── synopsis_ch2.json
├── information_schema.json
├── foreshadows.json
├── foreshadow_state.json
├── foreshadow_receipt_ch15.json
├── pipeline_state_ch3.json
├── pacing_state.json              # experimental metadata, not on the official path
├── pacing_receipt_ch3.json
├── transfer_ch3.json              # derived retrieval, not on the official path
├── information/
│   └── chapter_1.json
└── integration/
    └── integration_ch1.json
```

Authoritative data stays in the existing Author production locations, written
only by the Author commit journal:

```
story_bible.json  canonical_state.json  story_threads.json
memory_records.json  book_outline.json  generation_transactions/
sections (official committed prose)
```

## Migration from Existing Novels

Novels created before v2.50 will:
- Have no synopses (auto-generated on first pipeline use)
- Have no information schema (auto-generated based on story context)
- Have no foreshadows (empty state)
- Have no ChromaDB collection (created on first integration)

Previously persisted `pipeline_state_ch*.json` files still load: every field
added by the convergence refactor is defaulted, and the pipeline stores use
`extra="forbid"` only for fields they still define. A legacy `COMPLETED`
record that carries no Author commit evidence is **not** treated as committed;
it fails closed and requires an explicit `retry`.

A chapter with neither a frozen synopsis nor a BookOutline objective is
refused rather than generated from an invented goal such as `推进第N章剧情`.

## Integration with Author Production

- `run_chapter_pipeline(novel_id, chapter, author_service=...)` requires an
  `AuthorGenerationService`; the API obtains it from
  `story.runtime.get_author_runtime(user_id, novel_id).service`.
- One pipeline chapter maps to one official Author section
  (`production_chapter_ordinal=chapter`, `production_section_ordinal=1`).
- Style comes from the StoryBible `style_contract` / active `StyleProfile`
  through the Author chain. The pipeline no longer injects a
  `writer_prompt_prefix` of its own.
- Validation, repair, the revision guard and the transaction journal are the
  existing Author machinery, unmodified.
- `write_chapter_simplified()` remains in `llm_roles.py` strictly for
  experimental, smoke-test and legacy-compatibility use. It is not reachable
  from the production path.

### TaskManager Integration
- Task kind: `pipeline_chapter_generation`
- `POST /pipeline/generate/{chapter}` submits an async task
- Progress streamed via SSE at `/api/tasks/{task_id}/stream`
- One active task per novel enforced by TaskManager

## Frontend

The PipelineView (`frontend/src/dashboard/views/PipelineView.jsx`) provides:
- Synopsis editor with revision tracking
- Information schema field configuration
- Foreshadow status table with probability display
- Chapter confirmation UI with foreshadow mode selection
- Pipeline phase progress display (including `confirmed`)
- SSE progress subscription via existing task stream

## Testing

Key test files:

| File | Coverage |
|---|---|
| `test_pipeline_author_bridge.py` | Official chain reuse: commit, canon/thread advance, outline anchor for ch3, StoryBible + Canon in Writer context, idempotent rerun, validator rejection, retry attempts |
| `test_pipeline_confirmation_state.py` | `confirmed` state machine, revision freeze / fail-closed drift, route-level 409 and commit reporting |
| `test_pipeline_commit_semantics.py` | `COMPLETED` requires a verified Author commit; failures end in `failed`; crash replay costs no second Writer call |
| `test_pipeline_connectivity.py` | 3-chapter run across every module boundary, no provider |
| `test_pipeline_persistence.py` | Pipeline stores and ChromaDB |
| `test_foreshadow_selection.py` | Probability rules |
| `test_pipeline_writer_retry.py` | `write_chapter_simplified` retry (experimental role) |

Run tests:
```bash
python -m pytest backend/tests/ -q -W error
python -m pytest backend/tests/test_pipeline_author_bridge.py -v
```

All of the above are LLM-free: pipeline-owned roles use the `mock_llm` fixture
and the official Writer is a recording stand-in, so every real Author
validator, the repair gate and the commit journal stay in the path.
