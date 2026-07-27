"""Author-mode StoryBible, canonical state, mode, and section APIs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

import novel_manager
from auth import User, get_current_user
from sections.section_store import get_section_store
from story.event_execution import event_execution_plan_prompt_payload
from story.migrations import ensure_story_domain
from story.models import (
    GenerationModeUpdate,
    GenerationTransaction,
    SectionGoal,
    StoryBibleUpdate,
)
from story.narrative_contract import (
    NarrativeContractInput,
    narrative_contract_prompt_payload,
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
from story.section_budget import section_budget_plan_prompt_payload
from story.service import (
    GenerationRejected,
    RevisionChainBrokenError,
    StaleStoryBibleError,
)
from story.writing_plan import section_writing_plan_prompt_payload
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
    narrative_constraints: NarrativeContractInput = Field(
        default_factory=NarrativeContractInput
    )


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
            "candidate_history",
            "base_canonical_state",
            "base_story_threads",
            "base_memory_repository",
            "target_canonical_state",
            "target_story_threads",
            "target_memory_repository",
            "section_record",
        },
    )
    if transaction.narrative_contract:
        payload["narrative_contract"] = {
            **narrative_contract_prompt_payload(transaction.narrative_contract),
            "section_id": transaction.narrative_contract.section_id,
            "story_bible_revision": transaction.narrative_contract.story_bible_revision,
            "canonical_state_revision": (
                transaction.narrative_contract.canonical_state_revision
            ),
        }
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


@router.post("/sections/contract-preview")
async def preview_author_section_contract(
    novel_id: str,
    request: SectionGenerateRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    data_dir, _, _ = _owned_data_dir(current_user.id, novel_id)
    mode = GenerationModeStore(data_dir).load()
    if mode.mode != "author":
        _api_error(409, "MODE_MISMATCH", "正文契约预览只适用于作者模式")
    runtime = get_author_runtime(current_user.id, novel_id)
    contract = runtime.service.preview_contract(SectionGoal(**request.model_dump()))
    event_plan = runtime.service.preview_event_execution_plan(
        SectionGoal(**request.model_dump())
    )
    writing_plan = runtime.service.preview_section_writing_plan(
        SectionGoal(**request.model_dump())
    )
    budget_plan = runtime.service.preview_section_budget_plan(
        SectionGoal(**request.model_dump())
    )
    return {
        "narrative_contract": {
            **narrative_contract_prompt_payload(contract),
            "section_id": contract.section_id,
            "story_bible_revision": contract.story_bible_revision,
            "canonical_state_revision": contract.canonical_state_revision,
        },
        "event_execution_plan": event_execution_plan_prompt_payload(event_plan),
        "section_writing_plan": section_writing_plan_prompt_payload(writing_plan),
        "section_budget_plan": section_budget_plan_prompt_payload(budget_plan),
    }


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


@router.get("/long-run/status")
async def get_author_long_run_status(
    novel_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    """Small advanced-diagnostics aggregate; never exposes prose or prompts."""
    data_dir, _, _ = _owned_data_dir(current_user.id, novel_id)
    transactions = GenerationTransactionStore(data_dir).list_all()
    contract_reports = [
        item.narrative_validation_report
        for item in transactions
        if item.narrative_validation_report is not None
    ]
    generated = [item for item in transactions if item.phase != "prepared"]
    committed = [item for item in transactions if item.committed]
    repair_count = sum(item.repair_performed for item in generated)
    hard_rejects = sum(item.phase == "rejected" for item in transactions)
    latencies: list[float] = []
    for item in transactions:
        try:
            start = datetime.fromisoformat(item.created_at)
            end = datetime.fromisoformat(item.updated_at)
            latencies.append(max(0.0, (end - start).total_seconds()))
        except ValueError:
            continue
    token_total = sum(int(item.usage.get("total_tokens", 0)) for item in transactions)
    state_conflicts = sum(
        1
        for item in transactions
        for violation in (item.validation_report.violations if item.validation_report else [])
        if violation.severity == "high"
    )
    thread_repository = StoryThreadStore(data_dir).load()
    open_threads = sum(
        item.status not in {"resolved", "abandoned"}
        for item in thread_repository.threads.values()
    )
    return {
        "run_id": transactions[-1].id if transactions else "",
        "completed_sections": len(committed),
        "contract_pass_rate": round(
            sum(item.accepted for item in contract_reports) / len(contract_reports), 4
        )
        if contract_reports
        else 0.0,
        "repair_rate": round(repair_count / len(generated), 4) if generated else 0.0,
        "hard_reject_count": hard_rejects,
        "canonical_revision": CanonicalStateStore(data_dir).load().revision,
        "total_tokens": token_total,
        "average_latency_seconds": round(sum(latencies) / len(latencies), 3)
        if latencies
        else 0.0,
        "restart_recovery_count": sum(item.recovery_count for item in transactions),
        "stale_transaction_count": sum(
            item.phase == "stale_context" for item in transactions
        ),
        "state_conflict_count": state_conflicts,
        "threads_open": open_threads,
        "transaction_count": len(transactions),
    }


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
        except RevisionChainBrokenError as exc:
            updater.set(last_message=exc.transaction.error)
            raise RuntimeError(
                "REVISION_CHAIN_BROKEN: " + exc.transaction.error
            ) from exc
        except GenerationRejected as exc:
            narrative_codes = [
                item.code
                for item in (
                    exc.transaction.narrative_validation_report.violations
                    if exc.transaction.narrative_validation_report
                    else []
                )
            ]
            authority_codes = [
                item.code
                for item in (exc.transaction.validation_report.violations if exc.transaction.validation_report else [])
            ]
            updater.set(last_message="正文或权威状态契约未通过，未提交任何数据")
            raise RuntimeError(
                "契约验证未通过: "
                + ", ".join(narrative_codes + authority_codes)
            ) from exc
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
            "narrative_contract": (
                narrative_contract_prompt_payload(transaction.narrative_contract)
                if transaction.narrative_contract
                else {}
            ),
            "narrative_validation_report": (
                transaction.narrative_validation_report.model_dump(mode="json")
                if transaction.narrative_validation_report
                else {}
            ),
            "style_validation_report": transaction.style_validation_report,
            "event_execution_plan": (
                event_execution_plan_prompt_payload(transaction.event_execution_plan)
                if transaction.event_execution_plan
                else {}
            ),
            "section_writing_plan": (
                section_writing_plan_prompt_payload(transaction.section_writing_plan)
                if transaction.section_writing_plan
                else {}
            ),
            "section_budget_plan": (
                section_budget_plan_prompt_payload(transaction.section_budget_plan)
                if transaction.section_budget_plan
                else {}
            ),
            "initial_preflight_report": (
                transaction.initial_preflight_report.model_dump(mode="json")
                if transaction.initial_preflight_report
                else {}
            ),
            "final_preflight_report": (
                transaction.final_preflight_report.model_dump(mode="json")
                if transaction.final_preflight_report
                else {}
            ),
            "writer_first_pass_pass": transaction.writer_first_pass_pass,
            "writer_retry_count": transaction.writer_retry_count,
            "writer_retry_performed": transaction.writer_retry_performed,
            "initial_length_report": (
                transaction.initial_length_report.model_dump(mode="json")
                if transaction.initial_length_report
                else {}
            ),
            "final_length_report": (
                transaction.final_length_report.model_dump(mode="json")
                if transaction.final_length_report
                else {}
            ),
            "initial_ending_report": (
                transaction.initial_ending_report.model_dump(mode="json")
                if transaction.initial_ending_report
                else {}
            ),
            "final_ending_report": (
                transaction.final_ending_report.model_dump(mode="json")
                if transaction.final_ending_report
                else {}
            ),
            "initial_balance_report": (
                transaction.initial_balance_report.model_dump(mode="json")
                if transaction.initial_balance_report
                else {}
            ),
            "final_balance_report": (
                transaction.final_balance_report.model_dump(mode="json")
                if transaction.final_balance_report
                else {}
            ),
            "repair_plan": (
                transaction.repair_plan.model_dump(mode="json")
                if transaction.repair_plan
                else {}
            ),
            "repair_patches": (
                transaction.repair_patches.model_dump(mode="json")
                if transaction.repair_patches
                else {}
            ),
            "repair_patch_report": (
                transaction.repair_patch_report.model_dump(mode="json")
                if transaction.repair_patch_report
                else {}
            ),
            "repair_ignored_fields": transaction.repair_ignored_fields,
            "repair_audit_codes": transaction.repair_audit_codes,
            "repair_enforced_removals": transaction.repair_enforced_removals,
            "repair_performed": transaction.repair_performed,
            "committed": transaction.committed,
        }

    return _executor


__all__ = ["router"]
