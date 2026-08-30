"""API routes for the stateful chapter generation pipeline.

Endpoints cover:
  - Chapter synopsis CRUD
  - Information schema CRUD
  - Chapter generation preferences
  - User confirmation and chapter generation
  - Pipeline status
  - Foreshadow list and status
  - ChromaDB diagnostics
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import User, get_current_user
from story.stateful_pipeline.models import (
    ChapterGenerationPreference,
    ChapterPipelinePhase,
    ForeshadowMode,
)
from story.stateful_pipeline.service import (
    PipelineError,
    StatefulPipelineService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels/{novel_id}/pipeline", tags=["stateful-pipeline"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class SynopsisUpdateRequest(BaseModel):
    title: str | None = None
    synopsis: str | None = None


class SynopsisResponse(BaseModel):
    chapter: int
    title: str
    synopsis: str
    revision: int
    frozen: bool


class SchemaFieldRequest(BaseModel):
    key: str
    name: str
    description: str = ""


class SchemaUpdateRequest(BaseModel):
    fields: list[SchemaFieldRequest]


class SchemaResponse(BaseModel):
    revision: int
    source: str
    fields: list[dict[str, Any]]


class GenerationPreferenceRequest(BaseModel):
    chapter: int
    foreshadow_mode: str = "random"  # "random" | "fixed"
    foreshadow_count: int = Field(default=0, ge=0, le=2)


class ConfirmAndGenerateRequest(BaseModel):
    chapter: int
    foreshadow_mode: str = "random"
    foreshadow_count: int = Field(default=0, ge=0, le=2)


class ForeshadowResponse(BaseModel):
    id: str
    source_chapter: int
    summary: str
    status: str
    probability: float
    selected_once: bool
    discarded: bool
    next_eligible_chapter: int


class ForeshadowStateResponse(BaseModel):
    consecutive_selection_count: int
    discard_unlocked: bool
    last_selected_chapter: int | None


class PipelineStatusResponse(BaseModel):
    chapter: int
    phase: str
    synopsis_revision: int | None
    style_revision: int | None
    error_message: str | None


class ChromaStatusResponse(BaseModel):
    novel_id: str
    document_count: int


# ---------------------------------------------------------------------------
# Service Factory
# ---------------------------------------------------------------------------

_service_cache: dict[str, StatefulPipelineService] = {}


def _get_pipeline_service(novel_id: str) -> StatefulPipelineService:
    """Get or create pipeline service for a novel."""
    if novel_id not in _service_cache:
        import novel_manager
        data_dir = novel_manager.get_novel_dir(novel_id)
        _service_cache[novel_id] = StatefulPipelineService(data_dir)
    return _service_cache[novel_id]


def _sanitize_error(msg: str) -> str:
    """Remove sensitive info from error messages."""
    import re
    return re.sub(
        r"(?i)(?:api[_ -]?key|api[_ -]?secret|authorization|bearer\s+\S+|"
        r"\bsk-[A-Za-z0-9_-]{8,}|traceback\s+\(most recent call last\))",
        "[REDACTED]",
        msg,
    )


# ---------------------------------------------------------------------------
# Synopsis Endpoints
# ---------------------------------------------------------------------------


@router.get("/synopsis", response_model=list[SynopsisResponse])
async def get_synopses(
    novel_id: str,
    user: User = Depends(get_current_user),
):
    """Get all chapter synopses."""
    service = _get_pipeline_service(novel_id)
    synopses = service._synopsis_store.load_all(novel_id)
    return [
        SynopsisResponse(
            chapter=s.chapter_number,
            title=s.title,
            synopsis=s.synopsis,
            revision=s.revision,
            frozen=s.is_frozen,
        )
        for s in synopses
    ]


@router.get("/synopsis/{chapter}", response_model=SynopsisResponse)
async def get_synopsis(
    novel_id: str,
    chapter: int,
    user: User = Depends(get_current_user),
):
    """Get synopsis for a specific chapter."""
    service = _get_pipeline_service(novel_id)
    synopsis = service.get_synopsis(novel_id, chapter)
    if synopsis is None:
        raise HTTPException(status_code=404, detail="Synopsis not found")
    return SynopsisResponse(
        chapter=synopsis.chapter_number,
        title=synopsis.title,
        synopsis=synopsis.synopsis,
        revision=synopsis.revision,
        frozen=synopsis.is_frozen,
    )


@router.put("/synopsis/{chapter}", response_model=SynopsisResponse)
async def update_synopsis(
    novel_id: str,
    chapter: int,
    request: SynopsisUpdateRequest,
    user: User = Depends(get_current_user),
):
    """Update synopsis (user edit). Creates new revision."""
    service = _get_pipeline_service(novel_id)
    try:
        updated = service.update_synopsis(
            novel_id,
            chapter,
            title=request.title,
            synopsis=request.synopsis,
        )
        return SynopsisResponse(
            chapter=updated.chapter_number,
            title=updated.title,
            synopsis=updated.synopsis,
            revision=updated.revision,
            frozen=updated.is_frozen,
        )
    except Exception as exc:
        logger.warning("Synopsis update failed: %s", exc)
        raise HTTPException(status_code=400, detail=_sanitize_error(str(exc)))


@router.post("/synopsis/generate")
async def generate_synopses(
    novel_id: str,
    user: User = Depends(get_current_user),
):
    """Generate initial synopses for chapters 1 and 2."""
    service = _get_pipeline_service(novel_id)

    import novel_manager
    from story.persistence import StoryBibleStore

    data_dir = novel_manager.get_novel_dir(novel_id)
    bible_store = StoryBibleStore(data_dir)
    bible = bible_store.load()

    try:
        synopses = await service.generate_initial_synopses(
            novel_id=novel_id,
            story_bible=bible,
            genre=getattr(bible, "genre", "general"),
        )
        return {
            "synopses": [
                {
                    "chapter": s.chapter_number,
                    "title": s.title,
                    "synopsis": s.synopsis,
                }
                for s in synopses
            ]
        }
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=_sanitize_error(str(exc)))


# ---------------------------------------------------------------------------
# Information Schema Endpoints
# ---------------------------------------------------------------------------


@router.get("/schema", response_model=SchemaResponse | None)
async def get_schema(
    novel_id: str,
    user: User = Depends(get_current_user),
):
    """Get current information schema."""
    service = _get_pipeline_service(novel_id)
    schema = service.get_schema(novel_id)
    if schema is None:
        return None
    return SchemaResponse(
        revision=schema.revision,
        source=schema.source,
        fields=[
            {"key": f.key, "name": f.name, "description": f.description, "order": f.order}
            for f in schema.fields
        ],
    )


@router.put("/schema", response_model=SchemaResponse)
async def update_schema(
    novel_id: str,
    request: SchemaUpdateRequest,
    user: User = Depends(get_current_user),
):
    """Update information schema fields (user edit). Creates new revision."""
    service = _get_pipeline_service(novel_id)
    try:
        schema = service.update_schema(
            novel_id,
            fields=[f.model_dump() for f in request.fields],
        )
        return SchemaResponse(
            revision=schema.revision,
            source=schema.source,
            fields=[
                {"key": f.key, "name": f.name, "description": f.description, "order": f.order}
                for f in schema.fields
            ],
        )
    except Exception as exc:
        logger.warning("Schema update failed: %s", exc)
        raise HTTPException(status_code=400, detail=_sanitize_error(str(exc)))


@router.post("/schema/generate")
async def generate_schema(
    novel_id: str,
    user: User = Depends(get_current_user),
):
    """Auto-generate information schema based on story context."""
    service = _get_pipeline_service(novel_id)

    import novel_manager
    from story.persistence import StoryBibleStore

    data_dir = novel_manager.get_novel_dir(novel_id)
    bible_store = StoryBibleStore(data_dir)
    bible = bible_store.load()

    synopses = service._synopsis_store.load_all(novel_id)

    try:
        schema = await service.ensure_schema(
            novel_id=novel_id,
            story_bible=bible,
            genre=getattr(bible, "genre", "general"),
            synopses=synopses,
        )
        return SchemaResponse(
            revision=schema.revision,
            source=schema.source,
            fields=[
                {"key": f.key, "name": f.name, "description": f.description, "order": f.order}
                for f in schema.fields
            ],
        )
    except PipelineError as exc:
        raise HTTPException(status_code=500, detail=_sanitize_error(str(exc)))


# ---------------------------------------------------------------------------
# Foreshadow Endpoints
# ---------------------------------------------------------------------------


@router.get("/foreshadows", response_model=list[ForeshadowResponse])
async def get_foreshadows(
    novel_id: str,
    user: User = Depends(get_current_user),
):
    """Get all foreshadow records."""
    service = _get_pipeline_service(novel_id)
    records = service.get_foreshadows(novel_id)
    return [
        ForeshadowResponse(
            id=r.id,
            source_chapter=r.source_chapter,
            summary=r.summary,
            status=r.status.value,
            probability=r.current_probability,
            selected_once=r.selected_once,
            discarded=r.discarded,
            next_eligible_chapter=r.next_eligible_chapter,
        )
        for r in records
    ]


@router.get("/foreshadows/state", response_model=ForeshadowStateResponse)
async def get_foreshadow_state(
    novel_id: str,
    user: User = Depends(get_current_user),
):
    """Get foreshadow selection state."""
    service = _get_pipeline_service(novel_id)
    state = service.get_foreshadow_state(novel_id)
    return ForeshadowStateResponse(
        consecutive_selection_count=state.consecutive_selection_count,
        discard_unlocked=state.discard_unlocked,
        last_selected_chapter=state.last_selected_chapter,
    )


@router.get("/foreshadows/receipt/{chapter}")
async def get_selection_receipt(
    novel_id: str,
    chapter: int,
    user: User = Depends(get_current_user),
):
    """Get selection receipt for a chapter (for debugging/audit)."""
    service = _get_pipeline_service(novel_id)
    receipt = service.get_selection_receipt(novel_id, chapter)
    if receipt is None:
        raise HTTPException(status_code=404, detail="No receipt found")
    return receipt.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Pipeline Status Endpoints
# ---------------------------------------------------------------------------


@router.get("/status/{chapter}", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    novel_id: str,
    chapter: int,
    user: User = Depends(get_current_user),
):
    """Get pipeline status for a chapter."""
    service = _get_pipeline_service(novel_id)
    state = service.get_pipeline_state(novel_id, chapter)
    if state is None:
        return PipelineStatusResponse(
            chapter=chapter,
            phase="awaiting_user_confirmation",
            synopsis_revision=None,
            style_revision=None,
            error_message=None,
        )
    return PipelineStatusResponse(
        chapter=state.chapter_number,
        phase=state.phase.value,
        synopsis_revision=state.synopsis_revision,
        style_revision=state.style_revision,
        error_message=state.error_message,
    )


@router.get("/status")
async def get_current_status(
    novel_id: str,
    user: User = Depends(get_current_user),
):
    """Get current chapter number and overall pipeline state."""
    service = _get_pipeline_service(novel_id)
    current_chapter = service.get_current_chapter(novel_id)
    return {
        "current_chapter": current_chapter,
        "novel_id": novel_id,
    }


# ---------------------------------------------------------------------------
# Chapter Confirmation & Generation
# ---------------------------------------------------------------------------


@router.post("/confirm")
async def confirm_chapter(
    novel_id: str,
    request: ConfirmAndGenerateRequest,
    user: User = Depends(get_current_user),
):
    """Confirm chapter for generation (creates confirmation binding)."""
    service = _get_pipeline_service(novel_id)

    import novel_manager
    from story.persistence import CanonicalStateStore, StoryBibleStore

    data_dir = novel_manager.get_novel_dir(novel_id)
    bible_store = StoryBibleStore(data_dir)
    bible = bible_store.load()
    canon_store = CanonicalStateStore(data_dir)
    canon = canon_store.load()

    preference = ChapterGenerationPreference(
        novel_id=novel_id,
        chapter_number=request.chapter,
        foreshadow_mode=ForeshadowMode(request.foreshadow_mode),
        foreshadow_fixed_count=request.foreshadow_count,
    )

    try:
        confirmation = service.confirm_chapter(
            novel_id=novel_id,
            chapter=request.chapter,
            preference=preference,
            bible=bible,
            canon=canon,
            style_revision=0,  # TODO: get from active style
        )
        return {
            "confirmed": True,
            "chapter": request.chapter,
            "binding": confirmation.model_dump(mode="json"),
        }
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(str(exc)))


@router.post("/generate/{chapter}")
async def generate_chapter(
    novel_id: str,
    chapter: int,
    user: User = Depends(get_current_user),
):
    """Start chapter generation (requires prior confirmation).

    Submits a pipeline_chapter_generation task to the TaskManager.
    Progress is streamed via SSE at /api/tasks/{task_id}/stream.
    """
    service = _get_pipeline_service(novel_id)

    # Check if already confirmed
    state = service.get_pipeline_state(novel_id, chapter)
    if state is None or state.phase == ChapterPipelinePhase.AWAITING_CONFIRMATION:
        raise HTTPException(
            status_code=409,
            detail="Chapter requires user confirmation before generation. Call /confirm first.",
        )

    from tasks.task_manager import TaskConflict, get_task_manager

    task_manager = get_task_manager()

    async def pipeline_executor(updater, user_id: str, task_novel_id: str):
        """Execute the chapter generation pipeline."""
        import novel_manager
        from story.persistence import CanonicalStateStore, StoryBibleStore
        from story.stateful_pipeline.service import ConfirmationRequiredError

        data_dir = novel_manager.get_novel_dir(task_novel_id)
        bible_store = StoryBibleStore(data_dir)
        bible = bible_store.load()
        canon_store = CanonicalStateStore(data_dir)
        canon = canon_store.load()

        updater.set(current_words=0, last_message="准备上下文...")

        try:
            # Get confirmation from pipeline state
            confirmation = state.generation_preference
            if confirmation is None:
                raise ConfirmationRequiredError("No confirmation found")

            result_state = await service.run_chapter_pipeline(
                novel_id=task_novel_id,
                chapter=chapter,
                confirmation=confirmation,
                bible=bible,
                canon=canon,
                style_prefix="",  # TODO: get from active style
                chapter_goal=state.generation_preference.foreshadow_mode.value if state.generation_preference else "",
            )

            updater.set(last_message=f"第 {chapter} 章生成完成")
            return {
                "chapter": chapter,
                "phase": result_state.phase.value,
                "committed": result_state.phase == ChapterPipelinePhase.COMPLETED,
            }
        except ConfirmationRequiredError as exc:
            raise RuntimeError(f"Confirmation required: {exc}") from exc
        except PipelineError as exc:
            raise RuntimeError(f"Pipeline failed: {exc}") from exc

    try:
        task = task_manager.submit(
            user_id=user.id,
            novel_id=novel_id,
            kind="pipeline_chapter_generation",
            executor=pipeline_executor,
            chapter=chapter,
        )
        return {
            "status": "queued",
            "task_id": task.id,
            "chapter": chapter,
            "phase": state.phase.value,
            "stream_url": f"/api/tasks/{task.id}/stream",
        }
    except TaskConflict:
        raise HTTPException(
            status_code=409,
            detail="A generation task is already running for this novel.",
        )


# ---------------------------------------------------------------------------
# ChromaDB Diagnostics
# ---------------------------------------------------------------------------


@router.get("/chroma/status", response_model=ChromaStatusResponse)
async def get_chroma_status(
    novel_id: str,
    user: User = Depends(get_current_user),
):
    """Get ChromaDB document count for this novel."""
    service = _get_pipeline_service(novel_id)
    count = await service._chroma.count(novel_id)
    return ChromaStatusResponse(novel_id=novel_id, document_count=count)


@router.post("/chroma/rebuild")
async def rebuild_chroma(
    novel_id: str,
    user: User = Depends(get_current_user),
):
    """Rebuild ChromaDB from committed chapter information."""
    service = _get_pipeline_service(novel_id)

    # Load all chapter informations
    chapter_informations = []
    for ch in range(1, service.get_current_chapter(novel_id)):
        info = service._info_store.load(novel_id, ch)
        if info:
            chapter_informations.append(info.model_dump(mode="json"))

    schema = service.get_schema(novel_id)
    schema_revision = schema.revision if schema else 1

    try:
        count = await service._chroma.rebuild(
            novel_id=novel_id,
            chapter_informations=chapter_informations,
            schema_revision=schema_revision,
        )
        return {
            "rebuilt": True,
            "documents_written": count,
        }
    except Exception as exc:
        logger.error("Chroma rebuild failed: %s", exc)
        raise HTTPException(status_code=500, detail=_sanitize_error(str(exc)))
