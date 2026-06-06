"""v2.24 任务 REST + SSE 路由。

| Method | Path                          | 用途                          |
|--------|-------------------------------|-------------------------------|
| GET    | /api/tasks                    | 列出所有任务 (可按 novel 过滤)  |
| GET    | /api/tasks/{task_id}          | 单任务快照                     |
| POST   | /api/tasks/{task_id}/cancel   | 取消任务                       |
| GET    | /api/tasks/{task_id}/stream   | SSE 进度流                     |

注意: 创建任务的 POST 不在此模块, 由具体业务路由 (/api/section/generate 等)
自己挂钩 ``get_task_manager().create_task(...)``。这样业务层定义 executor,
任务层只负责生命周期。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from tasks.task_manager import TaskNotFound, get_task_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(novel_id: str | None = None) -> dict:
    mgr = get_task_manager()
    if novel_id:
        items = mgr.list_for_novel(novel_id)
    else:
        items = mgr.list_all()
    return {
        "count": len(items),
        "tasks": [t.model_dump(mode="json") for t in items],
    }


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    mgr = get_task_manager()
    try:
        t = mgr.get(task_id)
    except TaskNotFound:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    return t.model_dump(mode="json")


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict:
    mgr = get_task_manager()
    try:
        t = await mgr.cancel(task_id)
    except TaskNotFound:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    return {"ok": True, "task": t.model_dump(mode="json")}


@router.get("/{task_id}/stream")
async def stream_task(task_id: str):
    mgr = get_task_manager()
    # 提前校验, 避免 SSE 已经握手才 raise
    try:
        mgr.get(task_id)
    except TaskNotFound:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")

    async def event_generator():
        try:
            async for snapshot in mgr.watch(task_id):
                yield {
                    "event": "snapshot",
                    "data": snapshot.model_dump_json(),
                }
        except asyncio.CancelledError:
            # 客户端断开 — 不需要做事
            return
        except Exception as e:
            logger.exception("SSE stream for %s crashed: %s", task_id, e)
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())
