"""Author-mode StoryBible, canonical state, mode, and section APIs."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import novel_manager
from auth import User, get_current_user
from sections.section_store import get_section_store
from story.migrations import ensure_story_domain
from story.models import (
    GenerationModeUpdate,
    GenerationTransaction,
    SectionGoal,
    StoryBibleUpdate,
)
from story.persistence import (
    CanonicalStateStore,
    ContextManifestStore,
    GenerationModeStore,
    GenerationTransactionStore,
    RevisionConflict,
    StoryBibleStore,
    StoryThreadStore,
)
from story.runtime import drop_author_runtime, get_author_runtime
from story.service import GenerationRejected, StaleStoryBibleError
from tasks.task_manager import (
    ProgressUpdater,
    TaskConflict,
    TaskNotFound,
    get_task_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels/{novel_id}", tags=["author-story"])


class SectionGenerateRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=4000)
    viewpoint_character_id: str = ""
    location_id: str = ""
    involved_characters: list[str] = Field(default_factory=list, max_length=30)
    target_threads: list[str] = Field(default_factory=list, max_length=30)
    desired_length: int = Field(default=1800, ge=200, le=10000)


def _api_error(status: int, code: str, message: str, **details: Any) -> None:
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message, "details": details},
    )


def _owned_data_dir(user_id: str, novel_id: str) -> tuple[str, dict, Any]:
    try:
        novel = novel_manager.get_novel(user_id, novel_id)
    except ValueError:
        _api_error(404, "NOVEL_NOT_FOUND", "作品不存在")
    if novel is None:
        _api_error(404, "NOVEL_NOT_FOUND", "作品不存在")
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
    report = ensure_story_domain(data_dir, title=str(novel.get("title") or ""))
    return data_dir, novel, report


def _public_transaction(transaction: GenerationTransaction) -> dict[str, Any]:
    payload = transaction.model_dump(
        mode="json",
        exclude={
            "candidate",
            "base_canonical_state",
            "base_story_threads",
            "base_memory_repository",
            "target_canonical_state",
            "target_story_threads",
            "target_memory_repository",
            "section_record",
        },
    )
    return payload


@router.get("/story-bible")
async def get_story_bible(
    novel_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    data_dir, _, migration = _owned_data_dir(current_user.id, novel_id)
    return {
        "story_bible": StoryBibleStore(data_dir).load().model_dump(mode="json"),
        "migration": migration.model_dump(mode="json"),
        "authority": "highest_creative_contract",
    }


@router.put("/story-bible")
async def put_story_bible(
    novel_id: str,
    request: StoryBibleUpdate,
    current_user: User = Depends(get_current_user),
) -> dict:
    data_dir, _, _ = _owned_data_dir(current_user.id, novel_id)
    try:
        bible = StoryBibleStore(data_dir).update(request)
    except RevisionConflict as exc:
        _api_error(
            409,
            "REVISION_CONFLICT",
            "创作圣经已被其他会话更新，请刷新后重试",
            expected=exc.expected,
            actual=exc.actual,
        )
    drop_author_runtime(current_user.id, novel_id)
    novel_manager.touch_last_accessed(current_user.id, novel_id)
    return {"story_bible": bible.model_dump(mode="json")}


@router.get("/canonical-state")
async def get_canonical_state(
    novel_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    data_dir, _, migration = _owned_data_dir(current_user.id, novel_id)
    state = CanonicalStateStore(data_dir).load()
    return {
        "canonical_state": state.model_dump(mode="json"),
        "migration": migration.model_dump(mode="json"),
        "authority": "only_current_fact_source",
    }


@router.get("/story-threads")
async def get_story_threads(
    novel_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    data_dir, _, _ = _owned_data_dir(current_user.id, novel_id)
    repository = StoryThreadStore(data_dir).load()
    return repository.model_dump(mode="json")


@router.get("/generation-mode")
async def get_generation_mode(
    novel_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    data_dir, _, _ = _owned_data_dir(current_user.id, novel_id)
    config = GenerationModeStore(data_dir).load()
    return {
        **config.model_dump(mode="json"),
        "modes": {
            "author": "围绕 StoryBible 与章节目标，由单 Writer 生成并经统一 Validator 提交",
            "simulation": "实验性多 Agent 世界模拟，候选变化仍需统一 Validator 与 CanonicalState",
        },
    }


@router.put("/generation-mode")
async def put_generation_mode(
    novel_id: str,
    request: GenerationModeUpdate,
    current_user: User = Depends(get_current_user),
) -> dict:
    data_dir, _, _ = _owned_data_dir(current_user.id, novel_id)
    mode_store = GenerationModeStore(data_dir)
    previous = mode_store.load()
    try:
        config = mode_store.update(request)
    except RevisionConflict as exc:
        _api_error(
            409,
            "REVISION_CONFLICT",
            "生成模式已变化，请刷新后重试",
            expected=exc.expected,
            actual=exc.actual,
        )

    drop_author_runtime(current_user.id, novel_id)
    if config.mode == "simulation":
        # The expensive nine-agent graph is constructed only after this explicit
        # user choice, never while loading an author-mode novel.
        from tick_runtime import set_active_novel

        try:
            await run_in_threadpool(set_active_novel, current_user.id, novel_id)
        except Exception:
            logger.exception("simulation runtime initialization failed")
            try:
                mode_store.update(
                    GenerationModeUpdate(
                        expected_revision=config.revision,
                        mode=previous.mode,
                    )
                )
            except Exception:
                logger.exception("generation mode rollback failed")
            from tick_runtime import drop_cache

            await run_in_threadpool(drop_cache, current_user.id, novel_id)
            _api_error(
                503,
                "SIMULATION_RUNTIME_FAILED",
                "实验性世界模拟运行时初始化失败",
            )
    else:
        from tick_runtime import drop_cache

        await run_in_threadpool(drop_cache, current_user.id, novel_id)
    novel_manager.touch_last_accessed(current_user.id, novel_id)
    return config.model_dump(mode="json")


@router.post("/sections/generate")
async def generate_author_section(
    novel_id: str,
    request: SectionGenerateRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    data_dir, novel, _ = _owned_data_dir(current_user.id, novel_id)
    mode = GenerationModeStore(data_dir).load()
    if mode.mode != "author":
        _api_error(
            409,
            "MODE_MISMATCH",
            "当前为实验性世界模拟模式；请切回作者模式后按章节目标生成",
        )
    goal = SectionGoal(**request.model_dump())
    store = get_section_store(novel_id, data_dir=data_dir)
    chapter, section = store.next_position()
    executor = _make_author_executor(goal)
    manager = get_task_manager()
    try:
        task = await manager.create_task(
            user_id=current_user.id,
            novel_id=novel_id,
            novel_title=str(novel.get("title") or ""),
            kind="author_section_generation",
            executor=executor,
            target_words=goal.desired_length,
            min_words=200,
            max_ticks=2,
            chapter=chapter,
            section_no=section,
        )
    except TaskConflict as exc:
        _api_error(409, "TASK_CONFLICT", "该作品已有章节生成任务", reason=str(exc))
    novel_manager.touch_last_accessed(current_user.id, novel_id)
    return task.model_dump(mode="json")


@router.get("/sections/{task_or_section_id}/status")
async def get_author_section_status(
    novel_id: str,
    task_or_section_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    data_dir, _, _ = _owned_data_dir(current_user.id, novel_id)
    manager = get_task_manager()
    task_payload = None
    try:
        task = manager.get(task_or_section_id)
        if task.user_id != current_user.id or task.novel_id != novel_id:
            _api_error(404, "STATUS_NOT_FOUND", "生成任务或章节不存在")
        task_payload = task.model_dump(mode="json")
    except TaskNotFound:
        pass

    transactions = GenerationTransactionStore(data_dir)
    transaction_payload = None
    if transactions.exists(task_or_section_id):
        transaction = transactions.load(task_or_section_id)
        if transaction.user_id != current_user.id or transaction.novel_id != novel_id:
            _api_error(404, "STATUS_NOT_FOUND", "生成任务或章节不存在")
        transaction_payload = _public_transaction(transaction)

    section = get_section_store(novel_id, data_dir=data_dir).get_by_id(task_or_section_id)
    if task_payload is None and transaction_payload is None and section is None:
        _api_error(404, "STATUS_NOT_FOUND", "生成任务或章节不存在")
    return {
        "task": task_payload,
        "transaction": transaction_payload,
        "section": section.model_dump(mode="json") if section else None,
    }


@router.get("/context-manifest")
async def get_context_manifest(
    novel_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    data_dir, _, _ = _owned_data_dir(current_user.id, novel_id)
    manifest = ContextManifestStore(data_dir, novel_id=novel_id).load()
    return manifest.model_dump(mode="json")


def _make_author_executor(goal: SectionGoal):
    async def _executor(
        updater: ProgressUpdater,
        user_id: str,
        novel_id: str,
    ) -> dict[str, Any]:
        updater.set(tick_count=0, last_message="构建固定槽位上下文")
        runtime = get_author_runtime(user_id, novel_id)
        updater.set(tick_count=1, last_message="Writer 生成并执行统一一致性校验")
        try:
            transaction = await runtime.service.run(goal, request_id=updater.task_id)
        except StaleStoryBibleError as exc:
            updater.set(last_message=exc.transaction.error)
            raise RuntimeError(
                "STORY_BIBLE_REVISION_STALE: " + exc.transaction.error
            ) from exc
        except GenerationRejected as exc:
            codes = [
                item.code
                for item in (exc.transaction.validation_report.violations if exc.transaction.validation_report else [])
            ]
            updater.set(last_message="一致性验证未通过，未提交任何正文或状态")
            raise RuntimeError("一致性验证未通过: " + ", ".join(codes)) from exc
        updater.set(tick_count=2, last_message="验证通过，正文与权威状态已原子提交")
        section = runtime.service.sections.get_by_id(transaction.section_id)
        return {
            "result_title": section.title if section else "章节已提交",
            "result_word_count": section.word_count if section else 0,
            "chapter": section.chapter if section else None,
            "section_no": section.section if section else None,
            "transaction_id": transaction.id,
            "story_bible_revision": transaction.story_bible_revision,
            "canonical_state_revision": transaction.target_canonical_revision,
            "validation_report": (
                transaction.validation_report.model_dump(mode="json")
                if transaction.validation_report
                else {}
            ),
            "repair_performed": transaction.repair_performed,
            "committed": transaction.committed,
        }

    return _executor


__all__ = ["router"]
