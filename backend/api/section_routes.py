"""v2.24 — tick 驱动的节级 API。

| Method | Path                                | 用途                                |
|--------|-------------------------------------|-------------------------------------|
| POST   | /api/section/generate               | 创建续写下一节任务 (走任务队列)        |
| GET    | /api/section/list                   | 列出当前活跃 novel 的所有节            |
| GET    | /api/section/list/{novel_id}        | 列出指定 novel 的所有节                |

executor 控制流
---------------
1. 解析 next_position (chapter, section_no) — SectionStore 持有
2. 循环推 tick:
   2.1 await orchestrator.run_tick() → 拿 TickSummary
   2.2 读 orchestrator.last_narrator_output:
       - should_narrate=True  → 累积 narrative_text
       - should_narrate=False → 加入 SilentTickRecord
   2.3 updater.set(current_words, tick_count, current_tick)
   2.4 SectionCloser.decide_close → break if 切节
3. SectionCloser.close_section → 终稿 + 标题 + 补叙
4. SectionStore.append(TickSection) — JSONL 落盘
5. 自动小说命名 — 若仍是"未命名小说"用首节内容补标题
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import novel_manager
from agents.section_closer import (
    SectionCloser,
    SilentTickRecord,
    section_max_ticks,
    section_min_words,
    section_target_words,
)
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
from tick_runtime import get_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/section", tags=["section"])


# ---- Request 契约 -----------------------------------------------------------


class GenerateSectionRequest(BaseModel):
    """续写下一节请求。

    novel_id 不传时, 取 routes._active_novel_id (当前活跃小说)。
    """

    novel_id: str | None = Field(default=None, description="目标 novel; 不传走当前活跃")
    kind: TaskKind = Field(default="section_generation", description="任务类型")


# ---- 端点 -------------------------------------------------------------------


@router.post("/generate")
async def generate_section_task(req: GenerateSectionRequest):
    """创建一个"续写下一节"后台任务, 立即返回任务快照。

    前端用返回的 task_id 订阅 /api/tasks/{id}/stream 看进度, 最终读
    /api/section/list 拿到新节内容。
    """
    novel_id = req.novel_id or _resolve_active_novel_id()
    if not novel_id:
        raise HTTPException(status_code=400, detail="未指定 novel_id 且无活跃小说")

    novel = novel_manager.get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    novel_title = (novel.get("title") or "").strip()

    # 预校验 — runtime 必须能起 (避免在 task 内部抛失败态)
    try:
        get_runtime(novel_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"runtime init failed: {e}")

    # 注册 SectionStore (如尚未注册)
    data_dir = novel_manager.get_novel_data_dir(novel_id)
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
    return snap.model_dump(mode="json")


@router.get("/list")
async def list_sections_active():
    """列出活跃 novel 的全部 tick 驱动节。"""
    novel_id = _resolve_active_novel_id()
    if not novel_id:
        raise HTTPException(status_code=400, detail="无活跃小说")
    return _dump_sections(novel_id)


@router.get("/list/{novel_id}")
async def list_sections_for_novel(novel_id: str):
    novel = novel_manager.get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    return _dump_sections(novel_id)


# ---- 内部辅助 ---------------------------------------------------------------


def _resolve_active_novel_id() -> str | None:
    """从 routes 模块拿当前活跃 novel_id (循环 import 用延迟 import 防)。"""
    try:
        from api import routes as _routes
        return _routes._active_novel_id
    except Exception:
        return None


def _dump_sections(novel_id: str) -> dict:
    data_dir = novel_manager.get_novel_data_dir(novel_id)
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
    """工厂 — 把 closer / store / 章节号封进闭包, 返回符合 Task Executor 签名的协程。"""

    async def _executor(updater: ProgressUpdater, novel_id: str) -> dict:
        runtime = get_runtime(novel_id)
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
            # 推一个 tick (run_tick 内部已有 asyncio.Lock 保证序列化)
            tick_summary = await orch.run_tick()
            tick_count += 1
            current_tick = tick_summary.tick

            no = orch.last_narrator_output
            if no is None:
                # 极端 fallback — orchestrator 未设此字段 (不应发生)
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
                        summary=no.tick_summary_for_record or f"tick {current_tick}: 平静.",
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

        # 切节 — 生成补叙 + 标题 + 终稿
        updater.set(last_message="切节中: 生成补叙 + 标题")
        out = await closer.close_section(
            narrative_text=accumulated_text,
            silent_ticks=silent_records,
            chapter=chapter,
            section_no=section_no,
            novel_title=novel_title,
        )

        # 落盘 TickSection
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

        # 首节自动命名 — 若 novel 标题仍是 "未命名小说" 且这是第 1 章第 1 节
        if (
            chapter == 1
            and section_no == 1
            and novel_title in ("", "未命名小说")
        ):
            try:
                _auto_rename_novel(novel_id, content=out.final_content)
            except Exception as e:
                logger.warning("auto rename novel '%s' failed (non-fatal): %s", novel_id, e)

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


def _auto_rename_novel(novel_id: str, content: str) -> None:
    """首节自动命名 — 取前 200 字让 LLM 起 4-8 字小说名。

    仅当 novel.title 仍是 "未命名小说" 时调用 (调用方已校验)。
    与 routes._auto_generate_title 复用同思路, 但走独立路径 — 避免 legacy
    pipeline 状态泄漏到 tick 驱动节路径。
    """
    # 暂用确定性兜底: 取首句前 8 字。 LLM 命名 P3 / 后续可补。
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
        novel_manager.update_title(novel_id, candidate)
        logger.info("Auto-renamed novel '%s' to '%s'", novel_id, candidate)
    except Exception as e:
        logger.warning("update_title failed: %s", e)
