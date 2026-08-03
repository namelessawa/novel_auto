"""Durable whole-book job controls, committed reads and event streaming."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth import User, get_current_user
from story.persistence import PersistenceError, RevisionConflict
from story.production_models import (
    GenerationJob,
    GenerationJobControlRequest,
    ProductionChapterRecord,
    ProductionStartRequest,
)
from story.production_runtime import get_production_runtime
from story.production_service import (
    ProductionLeaseConflict,
    StaleProductionContract,
)

from api.production_routes import _owned_domain


router = APIRouter(prefix="/api/novels/{novel_id}", tags=["author-production"])
_SENSITIVE_TEXT = re.compile(
    r"(?i)(api[_ -]?(?:key|secret)|authorization|bearer\s+\S+|"
    r"\bsk-[A-Za-z0-9_-]{8,}|traceback\s+\(most recent call last\))"
)


def _error(
    status: int,
    code: str,
    message: str,
    **details: Any,
) -> NoReturn:
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message, "details": details},
    )


def _runtime(current_user: User, novel_id: str):
    domain, _ = _owned_domain(current_user.id, novel_id)
    return get_production_runtime(
        current_user.id,
        novel_id,
        data_dir=domain.data_dir,
        title=str(domain.novel.get("title") or ""),
    )


def _translate_domain_error(exc: Exception) -> NoReturn:
    if isinstance(exc, RevisionConflict):
        _error(
            409,
            "REVISION_CONFLICT",
            "数据已被其他会话更新，请重新载入",
            expected=exc.expected,
            actual=exc.actual,
        )
    if isinstance(exc, ProductionLeaseConflict):
        _error(
            409,
            "PRODUCTION_LEASE_CONFLICT",
            "已有生产进程持有该任务租约",
        )
    if isinstance(exc, StaleProductionContract):
        _error(
            409,
            "PRODUCTION_CONTRACT_STALE",
            "整书权威数据已变化，请确认后重新开始",
        )
    if isinstance(exc, KeyError):
        _error(404, "PRODUCTION_JOB_NOT_FOUND", "整书生产任务不存在")
    if isinstance(exc, (ValueError, PersistenceError)):
        message = (
            str(exc).splitlines()[0][:240]
            if str(exc)
            else "生产请求与当前权威状态不兼容"
        )
        if _SENSITIVE_TEXT.search(message):
            message = "生产请求与当前权威状态不兼容"
        _error(
            422,
            "PRODUCTION_REQUEST_INVALID",
            message,
        )
    _error(500, "PRODUCTION_INTERNAL_ERROR", "整书生产操作失败")


def _public_job(job: GenerationJob, runtime) -> dict[str, Any]:
    chapters = runtime.service.list_chapters(committed_only=True)
    completed_chars = sum(chapter.char_count for chapter in chapters)
    committed_sections = [
        section for chapter in chapters for section in chapter.sections
    ]
    payload = job.model_dump(
        mode="json",
        exclude={
            "requested_spec_snapshot",
            "requested_outline_snapshot",
            "requested_style_snapshot",
        },
    )
    target_chars = (
        job.requested_spec_snapshot.target_total_chars
        if job.requested_spec_snapshot is not None
        else 0
    )
    payload.update(
        completed_chars=completed_chars,
        committed_chars=completed_chars,
        completed_chapters=len(chapters),
        progress_percent=(
            round(completed_chars * 100 / target_chars, 2)
            if target_chars
            else 0
        ),
        provider_call_count=sum(
            int(section.prompt_tokens > 0 or section.completion_tokens > 0)
            for section in committed_sections
        ),
        latency_sample_count=sum(
            int(section.latency_ms > 0) for section in committed_sections
        ),
        last_committed_at=max(
            (chapter.committed_at for chapter in chapters),
            default="",
        ),
        story_bible_revision=job.requested_story_bible_revision,
    )
    return payload


def _public_chapter(
    chapter: ProductionChapterRecord,
    *,
    include_content: bool,
) -> dict[str, Any]:
    committed_sections = list(chapter.sections)
    transaction_ids = [section.transaction_id for section in committed_sections]
    story_bible_revisions = [
        section.story_bible_revision for section in committed_sections
    ]
    repair_total = sum(
        int(section.repair_performed) for section in committed_sections
    )
    latest_transaction_id = transaction_ids[-1] if transaction_ids else ""
    payload = chapter.model_dump(mode="json")
    payload.update(
        id=chapter.chapter_id,
        ordinal=chapter.chapter_ordinal,
        committed=True,
        objective=chapter.chapter_outline.objective,
        viewpoint_character_id=chapter.chapter_outline.viewpoint_character_id,
        location_id=chapter.chapter_outline.location_id,
        transaction_id=latest_transaction_id,
        committed_transaction_id=latest_transaction_id,
        transaction_ids=transaction_ids,
        story_bible_revision=(
            story_bible_revisions[-1] if story_bible_revisions else 0
        ),
        story_bible_revision_start=(
            story_bible_revisions[0] if story_bible_revisions else 0
        ),
        story_bible_revision_end=(
            story_bible_revisions[-1] if story_bible_revisions else 0
        ),
        canonical_revision=chapter.canonical_revision_end,
        canonical_state_revision=chapter.canonical_revision_end,
        repair_total=repair_total,
        repair_performed=repair_total > 0,
        style_profile_name=chapter.style_profile.name,
        style_profile_revision=chapter.style_profile.revision,
    )
    sections: list[dict[str, Any]] = []
    for section in chapter.sections:
        row = section.model_dump(mode="json")
        row.update(status="committed", phase="committed", committed=True)
        if not include_content:
            row.pop("content", None)
        sections.append(row)
    payload["sections"] = sections
    if include_content:
        payload["content"] = chapter.manuscript_text()
    return payload


@router.post("/production/start")
async def start_production(
    novel_id: str,
    request: ProductionStartRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    runtime = _runtime(current_user, novel_id)
    try:
        outcome = runtime.service.start(
            expected_spec_revision=request.expected_spec_revision,
            expected_outline_revision=request.expected_outline_revision,
        )
        if outcome.job.status in {"queued", "running", "pausing", "cancelling"}:
            runtime.schedule(outcome.job.id)
        return {
            "job": _public_job(runtime.service.get_job(outcome.job.id), runtime),
            "existing": outcome.existing,
        }
    except Exception as exc:
        _translate_domain_error(exc)


@router.post("/production/pause")
async def pause_production(
    novel_id: str,
    request: GenerationJobControlRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    runtime = _runtime(current_user, novel_id)
    try:
        job = runtime.service.pause(
            request.job_id,
            expected_revision=request.expected_revision,
        )
        return {"job": _public_job(job, runtime)}
    except Exception as exc:
        _translate_domain_error(exc)


@router.post("/production/resume")
async def resume_production(
    novel_id: str,
    request: GenerationJobControlRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    runtime = _runtime(current_user, novel_id)
    try:
        job = runtime.service.resume(
            request.job_id,
            expected_revision=request.expected_revision,
        )
        runtime.schedule(job.id)
        return {"job": _public_job(job, runtime)}
    except Exception as exc:
        _translate_domain_error(exc)


@router.post("/production/cancel")
async def cancel_production(
    novel_id: str,
    request: GenerationJobControlRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    runtime = _runtime(current_user, novel_id)
    try:
        job = runtime.service.cancel(
            request.job_id,
            expected_revision=request.expected_revision,
        )
        return {"job": _public_job(job, runtime)}
    except Exception as exc:
        _translate_domain_error(exc)


@router.post("/production/retry-failed")
async def retry_failed_production(
    novel_id: str,
    request: GenerationJobControlRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    runtime = _runtime(current_user, novel_id)
    try:
        job = runtime.service.retry_failed(
            request.job_id,
            expected_revision=request.expected_revision,
        )
        runtime.schedule(job.id)
        return {"job": _public_job(job, runtime)}
    except Exception as exc:
        _translate_domain_error(exc)


@router.get("/production/status")
async def production_status(
    novel_id: str,
    job_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    runtime = _runtime(current_user, novel_id)
    try:
        return {"job": _public_job(runtime.service.get_job(job_id), runtime)}
    except Exception as exc:
        _translate_domain_error(exc)


@router.get("/chapters")
async def list_committed_chapters(
    novel_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    runtime = _runtime(current_user, novel_id)
    chapters = runtime.service.list_chapters(committed_only=True)
    return {
        "chapters": [
            _public_chapter(chapter, include_content=False)
            for chapter in chapters
        ],
        "count": len(chapters),
    }


@router.get("/chapters/{chapter_id}")
async def get_committed_chapter(
    novel_id: str,
    chapter_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    runtime = _runtime(current_user, novel_id)
    try:
        chapter = runtime.service.get_chapter(
            chapter_id,
            committed_only=True,
        )
    except KeyError:
        _error(404, "COMMITTED_CHAPTER_NOT_FOUND", "正式章节不存在")
    return {"chapter": _public_chapter(chapter, include_content=True)}


@router.get("/production/events")
async def production_events(
    novel_id: str,
    job_id: str | None = Query(default=None),
    after_sequence: int = Query(default=0, ge=0),
    follow: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    runtime = _runtime(current_user, novel_id)
    try:
        job = runtime.service.get_job(job_id)
    except Exception as exc:
        _translate_domain_error(exc)

    async def stream():
        sequence = after_sequence
        idle_polls = 0
        while True:
            rows = runtime.service.events.after(job.id, sequence)
            for event in rows:
                sequence = event.sequence
                data = {
                    **event.payload,
                    "sequence": event.sequence,
                    "job_id": event.job_id,
                    "chapter_id": event.chapter_id,
                    "section_id": event.section_id,
                    "transaction_id": event.transaction_id,
                    "timestamp": event.created_at,
                }
                encoded = json.dumps(
                    data,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield (
                    f"id: {event.sequence}\n"
                    f"event: {event.type}\n"
                    f"data: {encoded}\n\n"
                )
            if not follow:
                return
            current = runtime.service.get_job(job.id)
            if current.status in {"failed", "paused", "cancelled", "completed"}:
                if not runtime.service.events.after(job.id, sequence):
                    return
            idle_polls += 1
            if idle_polls % 60 == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
