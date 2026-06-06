"""v2.25 — bootstrap_world 端点 + 链式首节触发。

| Method | Path                                       | 用途                       |
|--------|--------------------------------------------|----------------------------|
| POST   | /api/novels/{novel_id}/bootstrap-world     | 冷启动世界 (4 阶段 LLM)     |

为什么独立 router
------------------
bootstrap_world 跑 4 个 LLM 调用 (WorldState / Characters / OpenLoops /
StyleAnchors), 单次执行 30-60s。直接在 POST 里同步等会让前端连接超时
或阻塞 UI; 走任务队列让 TaskListPanel 显示阶段进度。

链式触发
--------
执行完 bootstrap_world 后, 如果调用方设置 ``also_generate_first_section``,
立即入队一个 bootstrap_section 任务接续生成首节 — 用户一次操作触发两段
异步工作, 但每段独立可观测可取消。

为什么不放到 section_routes
-----------------------------
section_routes 关注"已种世界 → 推 tick → 切节"; bootstrap_routes 关注
"冷启动 / 给空世界喂种子"。两者契约层级不同。
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import novel_manager
from bootstrap_prompts import bootstrap_world
from tasks.task_manager import (
    ProgressUpdater,
    TaskConflict,
    get_task_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bootstrap"])


# 默认值与 bootstrap_prompts.py main() 对齐 — 让 API 用户拿到与 CLI 同样的
# 兜底, 而不是不传字段就 422。
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
async def bootstrap_world_endpoint(novel_id: str, req: BootstrapWorldRequest):
    """冷启动一个空小说 — 4 阶段种子化, 完成后可选链式触发首节。"""
    novel = novel_manager.get_novel(novel_id)
    if novel is None:
        raise HTTPException(status_code=404, detail=f"novel {novel_id!r} 不存在")
    novel_title = (novel.get("title") or "").strip()

    executor = _make_bootstrap_world_executor(
        novel_id=novel_id,
        seed=req.seed,
        positioning=req.positioning,
        references=req.references,
        also_generate_first_section=req.also_generate_first_section,
    )

    mgr = get_task_manager()
    try:
        snap = await mgr.create_task(
            novel_id=novel_id,
            novel_title=novel_title,
            kind="bootstrap_world",
            executor=executor,
            target_words=0,  # bootstrap 不以字数衡量
            min_words=0,
            max_ticks=4,  # 4 阶段, 借用 max_ticks 字段当总步数
        )
    except TaskConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    return snap.model_dump(mode="json")


# ---- 内部 — executor 工厂 --------------------------------------------------


def _make_bootstrap_world_executor(
    *,
    novel_id: str,
    seed: str,
    positioning: str,
    references: str,
    also_generate_first_section: bool,
):
    """工厂 — 把 bootstrap_world 包成 Task Executor 协程。

    阶段进度通过 ``updater.set(tick_count=N, last_message=...)`` 推送 —
    bootstrap_world 自身的 4 阶段映射到 tick_count 1-4。
    """

    async def _executor(updater: ProgressUpdater, runtime_novel_id: str) -> dict:
        # runtime_novel_id 来自 Task 创建时绑定的 novel_id, 与闭包里的应当一致
        data_dir = novel_manager.get_novel_data_dir(novel_id)
        os.makedirs(data_dir, exist_ok=True)

        updater.set(tick_count=0, last_message="启动冷启动流程")

        # bootstrap_world 内部已有 logger.info 输出每阶段进度, 但它不会调 updater.
        # 这里包一层 — 调用 bootstrap_world 一次, 它内部串行跑 4 阶段;
        # 我们在调用前后更新 updater (粗粒度), 阶段细节看后端日志。
        #
        # 想要细粒度阶段更新就要改造 bootstrap_world 接受一个 progress 回调;
        # 那样改 bootstrap_prompts.py 是更大动作, P0 先粗粒度上线。
        updater.set(tick_count=1, last_message="生成世界状态 / 角色 / 伏笔 / 风格锚点 …")
        try:
            ts = await bootstrap_world(
                novel_id=novel_id,
                data_dir=data_dir,
                seed=seed,
                positioning=positioning,
                references=references,
            )
        except Exception as e:
            logger.exception("bootstrap_world failed for novel '%s'", novel_id)
            raise

        # bootstrap 改了 tick_state.json, 必须让 TickRuntime 重读 — 否则
        # 在内存里仍是创建小说时的空 state, character_agents 为 0。
        _reload_runtime(novel_id)

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
            chained_id = await _spawn_chained_first_section(novel_id)
            result["chained_section_task_id"] = chained_id
            updater.set(
                last_message=f"已链式触发首节生成任务 {chained_id or '(skip)'}",
            )

        return result

    return _executor


def _reload_runtime(novel_id: str) -> None:
    """强制 TickRuntime 重读这个 novel 的 TickState + CharacterAgent 重建。

    bootstrap_world 直接写 tick_state.json, 但 v2.15 注册表里已有的 runtime
    实例还保留着创建小说时的空 state — 必须把这个 runtime 从注册表里清掉,
    下次 get_runtime 才会从盘上重新加载。
    """
    from tick_runtime import _runtimes, _active_novel_id, set_active_novel

    rt = _runtimes.pop(novel_id, None)
    if rt is not None:
        try:
            rt.close()
        except Exception as e:
            logger.warning("close stale runtime for '%s' failed: %s", novel_id, e)
    # 如果它是 active, 重新切回去 (会触发 set_active_novel 内的 get_runtime → 新实例)
    if _active_novel_id == novel_id:
        try:
            set_active_novel(novel_id)
        except Exception as e:
            logger.warning("re-set_active_novel('%s') failed: %s", novel_id, e)


async def _spawn_chained_first_section(novel_id: str) -> str:
    """bootstrap_world 完成后立即入队首节生成 — 返回 task_id 或空串。

    复用 section_routes 的 executor 工厂, 不引入新代码路径。
    """
    from agents.section_closer import SectionCloser
    from api.section_routes import _make_section_executor
    from sections.section_store import get_section_store

    novel = novel_manager.get_novel(novel_id)
    novel_title = (novel.get("title") if novel else "") or ""
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
