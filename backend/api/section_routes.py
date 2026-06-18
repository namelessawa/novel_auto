"""v2.24 — tick 驱动的节级 API (v2.26 加 user 隔离)。

| Method | Path                                | 用途                                |
|--------|-------------------------------------|-------------------------------------|
| POST   | /api/section/generate               | 创建续写下一节任务 (走任务队列)        |
| GET    | /api/section/list                   | 列出当前活跃 novel 的所有节            |
| GET    | /api/section/list/{novel_id}        | 列出指定 novel 的所有节                |

所有端点要求 ``Depends(get_current_user)`` —  novel_manager + runtime
都按 user_id 隔离。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import novel_manager
from agents.section_closer import (
    SectionCloser,
    SilentTickRecord,
)
from auth import User, get_current_user
from sections.section_store import (
    SectionStore,
    TickSection,
    get_section_store,
)
from tasks.task_manager import (
    ProgressUpdater,
    TaskConflict,
    TaskKind,
    get_task_manager,
)
from tick_runtime import get_active_novel_id, get_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/section", tags=["section"])


# ---- Request 契约 -----------------------------------------------------------


class GenerateSectionRequest(BaseModel):
    novel_id: str | None = Field(default=None, description="目标 novel; 不传走当前活跃")
    kind: TaskKind = Field(default="section_generation", description="任务类型")


# ---- 端点 -------------------------------------------------------------------


@router.post("/generate")
async def generate_section_task(
    req: GenerateSectionRequest, current_user: User = Depends(get_current_user)
):
    novel_id = req.novel_id or get_active_novel_id(current_user.id)
    if not novel_id:
        raise HTTPException(status_code=400, detail="未指定 novel_id 且无活跃小说")

    novel = novel_manager.get_novel(current_user.id, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    novel_title = (novel.get("title") or "").strip()

    try:
        get_runtime(current_user.id, novel_id)
    except Exception as e:
        # 不要把 str(e) 直接回显给前端 — 内部异常信息 (路径 / 栈片段) 可能泄露给攻击者
        logger.exception(
            "runtime init failed user=%s novel=%s", current_user.id, novel_id
        )
        raise HTTPException(
            status_code=503,
            detail="后端运行时初始化失败, 请稍后重试或联系管理员",
        ) from e

    data_dir = novel_manager.get_novel_data_dir(current_user.id, novel_id)
    store = get_section_store(novel_id, data_dir=data_dir)
    next_chapter, next_section = store.next_position()

    closer = SectionCloser()
    executor = _make_section_executor(
        closer=closer,
        store=store,
        novel_title=novel_title,
        chapter=next_chapter,
        section_no=next_section,
    )

    mgr = get_task_manager()
    try:
        snap = await mgr.create_task(
            user_id=current_user.id,
            novel_id=novel_id,
            novel_title=novel_title,
            kind=req.kind,
            executor=executor,
            target_words=closer.target_words,
            min_words=closer.min_words,
            max_ticks=closer.max_ticks,
            chapter=next_chapter,
            section_no=next_section,
        )
    except TaskConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    novel_manager.touch_last_accessed(current_user.id, novel_id)
    return snap.model_dump(mode="json")


@router.get("/list")
async def list_sections_active(current_user: User = Depends(get_current_user)):
    novel_id = get_active_novel_id(current_user.id)
    if not novel_id:
        raise HTTPException(status_code=400, detail="无活跃小说")
    return _dump_sections(current_user.id, novel_id)


@router.get("/list/{novel_id}")
async def list_sections_for_novel(
    novel_id: str, current_user: User = Depends(get_current_user)
):
    novel = novel_manager.get_novel(current_user.id, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    return _dump_sections(current_user.id, novel_id)


# ---- 内部辅助 ---------------------------------------------------------------


def _dump_sections(user_id: str, novel_id: str) -> dict:
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
    store = get_section_store(novel_id, data_dir=data_dir)
    items = store.list_all()
    return {
        "novel_id": novel_id,
        "count": len(items),
        "sections": [it.model_dump(mode="json") for it in items],
    }


def _make_section_executor(
    *,
    closer: SectionCloser,
    store: SectionStore,
    novel_title: str,
    chapter: int,
    section_no: int,
):
    """v2.26 — executor 签名增加 user_id (位置参数 2)。"""

    async def _executor(updater: ProgressUpdater, user_id: str, novel_id: str) -> dict:
        runtime = get_runtime(user_id, novel_id)
        orch = runtime.orchestrator

        tick_start = orch.current_tick
        narrative_parts: list[str] = []
        silent_records: list[SilentTickRecord] = []
        accumulated_text = ""
        tick_count = 0
        last_decision_reason = ""

        updater.set(
            current_words=0,
            tick_count=0,
            current_tick=tick_start,
            last_message=f"准备生成 第{chapter}章 第{section_no}节",
        )

        while True:
            tick_summary = await orch.run_tick()
            tick_count += 1
            current_tick = tick_summary.tick

            no = orch.last_narrator_output
            if no is None:
                silent_records.append(
                    SilentTickRecord(
                        tick=current_tick,
                        summary=f"tick {current_tick}: (无 Narrator 输出记录)",
                        skip_reason="no_narrator_output_cached",
                    )
                )
            elif no.should_narrate and no.narrative_text:
                narrative_parts.append(no.narrative_text)
                accumulated_text = "\n\n".join(narrative_parts)
            else:
                silent_records.append(
                    SilentTickRecord(
                        tick=current_tick,
                        summary=no.tick_summary_for_record
                        or f"tick {current_tick}: 平静.",
                        skip_reason=no.skip_reason,
                    )
                )

            words = _count_words(accumulated_text)
            updater.set(
                current_words=words,
                tick_count=tick_count,
                current_tick=current_tick,
                last_message=(
                    f"tick {current_tick} · "
                    + ("已叙述" if no and no.should_narrate else "沉默")
                ),
            )

            decision = await closer.decide_close(
                narrative_text=accumulated_text,
                tick_count=tick_count,
                novel_title=novel_title,
            )
            last_decision_reason = decision.reason
            if decision.should_close:
                break

        updater.set(last_message="切节中: 生成补叙 + 标题")
        out = await closer.close_section(
            narrative_text=accumulated_text,
            silent_ticks=silent_records,
            chapter=chapter,
            section_no=section_no,
            novel_title=novel_title,
        )

        tick_end = orch.current_tick
        section_record = TickSection(
            chapter=chapter,
            section=section_no,
            title=out.title,
            content=out.final_content,
            word_count=out.word_count,
            tick_start=tick_start,
            tick_end=tick_end,
            tick_count=tick_count,
            silent_tick_count=len(silent_records),
            closure_supplement=out.closure_supplement,
            created_at=TickSection.now_iso(),
        )
        store.append(section_record)

        if (
            chapter == 1
            and section_no == 1
            and novel_title in ("", "未命名小说")
        ):
            try:
                _auto_rename_novel(user_id, novel_id, content=out.final_content)
            except Exception as e:
                logger.warning(
                    "auto rename novel '%s' failed (non-fatal): %s", novel_id, e
                )

        # 写入完成 → 刷新 last_accessed_at
        try:
            novel_manager.touch_last_accessed(user_id, novel_id)
        except Exception as e:
            logger.warning("touch_last_accessed failed: %s", e)

        updater.set(
            last_message=(
                f"完成 第{chapter}章 第{section_no}节 · "
                f"{out.word_count} 字 · {tick_count} tick · "
                f"切节: {last_decision_reason}"
            ),
        )
        return {
            "result_title": out.title,
            "result_word_count": out.word_count,
            "chapter": chapter,
            "section_no": section_no,
        }

    return _executor


def _count_words(text: str) -> int:
    if not text:
        return 0
    return sum(1 for ch in text if not ch.isspace())


def _auto_rename_novel(user_id: str, novel_id: str, content: str) -> None:
    text = content.strip()
    if not text:
        return
    for sep in ("。", "!", "?", "!", "?", "\n"):
        idx = text.find(sep)
        if 0 < idx <= 50:
            text = text[:idx]
            break
    candidate = text.strip()[:8] or "未命名小说"
    if candidate == "未命名小说":
        return
    try:
        novel_manager.update_title(user_id, novel_id, candidate)
        logger.info("Auto-renamed novel '%s' to '%s'", novel_id, candidate)
    except Exception as e:
        logger.warning("update_title failed: %s", e)
