"""v2.24 任务 REST + SSE 路由 (v2.26 加 user_id 隔离)。

| Method | Path                          | 用途                          |
|--------|-------------------------------|-------------------------------|
| GET    | /api/tasks                    | 列出当前用户任务 (可按 novel) |
| GET    | /api/tasks/{task_id}          | 单任务快照 (校验 ownership)   |
| POST   | /api/tasks/{task_id}/cancel   | 取消任务                      |
| GET    | /api/tasks/{task_id}/stream   | SSE 进度流                    |

注意: 创建任务的 POST 不在此模块, 由具体业务路由 (/api/section/generate 等)
自己挂钩 ``get_task_manager().create_task(..., user_id=...)``。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from auth import User, get_current_user
from tasks.task_manager import TaskNotFound, get_task_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _check_ownership(task, user_id: str) -> None:
    """task.user_id 与请求者不匹配 → 404 (不泄露任务存在性)。

    v2.37 — 严格比较: 此前 ``task.user_id and ...`` 让 user_id=="" 的任务对
    任何登录用户可见/可取消。所有 create_task 调用点都强制传 user_id (auth
    关闭时为 "_legacy"), 空 user_id 的遗留任务被一律 404 是期望行为。
    """
    if task.user_id != user_id:
        raise HTTPException(status_code=404, detail="task not found")


@router.get("")
async def list_tasks(
    novel_id: str | None = None,
    current_user: User = Depends(get_current_user),
) -> dict:
    mgr = get_task_manager()
    if novel_id:
        items = mgr.list_for_user_and_novel(current_user.id, novel_id)
    else:
        items = mgr.list_for_user(current_user.id)
    return {
        "count": len(items),
        "tasks": [t.model_dump(mode="json") for t in items],
    }


@router.get("/{task_id}")
async def get_task(
    task_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    mgr = get_task_manager()
    try:
        t = mgr.get(task_id)
    except TaskNotFound:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    _check_ownership(t, current_user.id)
    return t.model_dump(mode="json")


@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str, current_user: User = Depends(get_current_user)
) -> dict:
    mgr = get_task_manager()
    try:
        t = mgr.get(task_id)
    except TaskNotFound:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    _check_ownership(t, current_user.id)
    try:
        t = await mgr.cancel(task_id)
    except TaskNotFound:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    return {"ok": True, "task": t.model_dump(mode="json")}


@router.get("/{task_id}/stream")
async def stream_task(
    task_id: str, current_user: User = Depends(get_current_user)
):
    mgr = get_task_manager()
    # 提前校验, 避免 SSE 已经握手才 raise
    try:
        t = mgr.get(task_id)
    except TaskNotFound:
        raise HTTPException(status_code=404, detail=f"task {task_id!r} not found")
    _check_ownership(t, current_user.id)

    async def event_generator():
        try:
            async for snapshot in mgr.watch(task_id):
                yield {
                    "event": "snapshot",
                    "data": snapshot.model_dump_json(),
                }
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.exception("SSE stream for %s crashed: %s", task_id, e)
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())
