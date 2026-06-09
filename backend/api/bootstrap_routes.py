"""v2.25 — bootstrap_world 端点 + 链式首节触发 (v2.26 加 user 隔离)。

| Method | Path                                       | 用途                       |
|--------|--------------------------------------------|----------------------------|
| POST   | /api/novels/{novel_id}/bootstrap-world     | 冷启动世界 (4 阶段 LLM)     |

novel_id 路径参数下, 强制校验当前用户拥有该 novel — 否则 404 (不泄露存在性)。
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import novel_manager
from auth import User, get_current_user
from bootstrap_prompts import bootstrap_world
from tasks.task_manager import (
    ProgressUpdater,
    TaskConflict,
    get_task_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bootstrap"])

DEFAULT_POSITIONING = "古典含蓄、心理白描、节奏舒缓、避免华丽辞藻"
DEFAULT_REFERENCES = "Le Guin / 古龙"


class BootstrapWorldRequest(BaseModel):
    seed: str = Field(min_length=1, description="世界种子描述 (主题 / 设定)")
    positioning: str = Field(
        default=DEFAULT_POSITIONING,
        description="作品定位 (文风 / 节奏)",
    )
    references: str = Field(
        default=DEFAULT_REFERENCES,
        description="参考作家 / 作品",
    )
    also_generate_first_section: bool = Field(
        default=True,
        description="bootstrap 完成后是否立即入队首节生成任务",
    )


@router.post("/api/novels/{novel_id}/bootstrap-world")
async def bootstrap_world_endpoint(
    novel_id: str,
    req: BootstrapWorldRequest,
    current_user: User = Depends(get_current_user),
):
    """冷启动一个空小说 — 4 阶段种子化, 完成后可选链式触发首节。"""
    novel = novel_manager.get_novel(current_user.id, novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    novel_title = (novel.get("title") or "").strip()

    executor = _make_bootstrap_world_executor(
        seed=req.seed,
        positioning=req.positioning,
        references=req.references,
        title=novel_title,
        also_generate_first_section=req.also_generate_first_section,
    )

    mgr = get_task_manager()
    try:
        snap = await mgr.create_task(
            user_id=current_user.id,
            novel_id=novel_id,
            novel_title=novel_title,
            kind="bootstrap_world",
            executor=executor,
            target_words=0,
            min_words=0,
            max_ticks=4,
        )
    except TaskConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    novel_manager.touch_last_accessed(current_user.id, novel_id)
    return snap.model_dump(mode="json")


# ---- 内部 — executor 工厂 --------------------------------------------------


def _make_bootstrap_world_executor(
    *,
    seed: str,
    positioning: str,
    references: str,
    title: str,
    also_generate_first_section: bool,
):
    async def _executor(
        updater: ProgressUpdater, user_id: str, novel_id: str
    ) -> dict:
        data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
        os.makedirs(data_dir, exist_ok=True)

        updater.set(tick_count=0, last_message="启动冷启动流程")
        updater.set(
            tick_count=1,
            last_message="生成世界状态 / 角色 / 伏笔 / 风格锚点 …",
        )
        try:
            ts = await bootstrap_world(
                novel_id=novel_id,
                data_dir=data_dir,
                seed=seed,
                positioning=positioning,
                references=references,
                title=title,
            )
        except Exception:
            logger.exception("bootstrap_world failed for novel '%s'", novel_id)
            raise

        # bootstrap 直写盘 — 让 runtime 重读 (close + 重建)
        _reload_runtime(user_id, novel_id)

        updater.set(
            tick_count=4,
            last_message=(
                f"种子化完成: {len(ts.list_character_profiles())} 角色 / "
                f"{ts.get_open_loop_count()} 伏笔 / "
                f"{len(ts.list_style_anchors())} 风格锚点"
            ),
        )

        result: dict = {
            "result_title": "世界种子已就位",
            "result_word_count": 0,
        }

        if also_generate_first_section:
            chained_id = await _spawn_chained_first_section(user_id, novel_id)
            result["chained_section_task_id"] = chained_id
            updater.set(
                last_message=f"已链式触发首节生成任务 {chained_id or '(skip)'}",
            )

        novel_manager.touch_last_accessed(user_id, novel_id)
        return result

    return _executor


def _reload_runtime(user_id: str, novel_id: str) -> None:
    """v2.26 — drop + 重建该 (user, novel) runtime, 强制重读盘。"""
    from tick_runtime import drop_runtime

    drop_runtime(user_id, novel_id)


async def _spawn_chained_first_section(user_id: str, novel_id: str) -> str:
    from agents.section_closer import SectionCloser
    from api.section_routes import _make_section_executor
    from sections.section_store import get_section_store

    novel = novel_manager.get_novel(user_id, novel_id)
    novel_title = (novel.get("title") if novel else "") or ""
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
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
            user_id=user_id,
            novel_id=novel_id,
            novel_title=novel_title,
            kind="bootstrap_section",
            executor=executor,
            target_words=closer.target_words,
            min_words=closer.min_words,
            max_ticks=closer.max_ticks,
            chapter=next_chapter,
            section_no=next_section,
        )
        return snap.id
    except TaskConflict as e:
        logger.warning("chained section task conflict for '%s': %s", novel_id, e)
        return ""
