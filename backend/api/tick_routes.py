"""tick_routes — FastAPI 路由, 暴露 Orchestrator 的 tick 控制与诊断 API。

v2.26 multi-tenant 改造
-----------------------
* 旧 ``_container`` 单例彻底删除 — 每请求经 ``Depends(get_user_runtime)``
  解析到 ``(current_user.id, user 的 active novel_id)`` → TickRuntime。
* ``set_orchestrator_dependencies`` 保留为 no-op 兼容 (tick_runtime.register_to_routes
  仍调用它, 但不再有实际作用)。

| Method | Path                          | 用途                                  |
|--------|-------------------------------|---------------------------------------|
| GET    | /api/tick/status              | 当前 tick / 暂停态 / OpenLoop 数      |
| POST   | /api/tick/run                 | 同步执行 1 个 tick(管理员手动)        |
| POST   | /api/tick/pause               | 暂停后续自动循环                       |
| POST   | /api/tick/resume              | 恢复                                  |
| POST   | /api/tick/inject-event        | 手动注入 Event                        |
| GET    | /api/tick/open-loops          | 当前所有开放伏笔                       |
| GET    | /api/tick/history             | 最近 N 个 TickSummary                  |
| GET    | /api/tick/event-stats         | Showrunner 视角的事件统计              |
| GET    | /api/tick/style-anchors       | 已注册的风格锚点                       |
| GET    | /api/tick/character-states    | 全部 CharacterState                   |
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from memory_system.models import Event, EventKind, OpenLoop

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tick", tags=["tick"])


# --- 依赖解析 (request-scoped) ---------------------------------------------
# tick_runtime 与 auth 在 Depends 内部 import — 避免模块加载期循环。
def _resolve_runtime(*, _user_dep=None):
    """Depends 入口: 解析当前请求用户 → 该用户活跃 novel 的 TickRuntime。

    实际签名通过 _make_resolver() 在路由注册期注入 — 这层 wrapper 让模块
    导入阶段不触发 tick_runtime / auth 的解析, 打破循环。
    """
    from auth import get_current_user  # noqa: F401 — Depends 注入时使用
    from tick_runtime import get_runtime

    # 这个分支永远不会直接被调; 真正生效的是 _make_resolver 返回的函数
    raise RuntimeError("_resolve_runtime should not be called directly")


def _make_resolver():
    from auth import User, get_current_user
    from tick_runtime import TickRuntime, get_runtime

    def _resolve(user: User = Depends(get_current_user)) -> TickRuntime:
        return get_runtime(user.id)

    return _resolve


# 路由 Depends 用这个 — 它在首次调用时才解析 tick_runtime / auth (避开模块加载循环)
_runtime_dep = None


def _get_runtime_dep():
    global _runtime_dep
    if _runtime_dep is None:
        _runtime_dep = _make_resolver()
    return _runtime_dep


class _LegacyContainer:
    """v2.26 兼容 shim — 旧测试 (test_orchestrator_concurrency / test_tick_runtime_registry)
    通过 ``from api.tick_routes import _container`` 读取注入的引用。

    新代码不再使用; 仅供旧测试 collection 通过。
    """

    orchestrator: Any = None
    tick_state: Any = None
    tick_db: Any = None


_container = _LegacyContainer()


def set_orchestrator_dependencies(
    *,
    orchestrator: Any | None = None,
    tick_state: Any | None = None,
    tick_db: Any | None = None,
) -> None:
    """v2.26 兼容 shim — multi-tenant 后由 Depends 完成实际解析。

    为兼容旧测试, 把传入的引用同步到 ``_container`` 上 (但运行时路由不读它)。
    """
    if orchestrator is not None:
        _container.orchestrator = orchestrator
    if tick_state is not None:
        _container.tick_state = tick_state
    if tick_db is not None:
        _container.tick_db = tick_db


# 让模块导入期就触发 _make_resolver (此时 tick_runtime 已不再 import 本模块, 安全)
_resolve_runtime = _get_runtime_dep()


# --- 路由 -----------------------------------------------------------------


class TickStatusResponse(BaseModel):
    current_tick: int
    world_time: int
    is_paused: bool
    open_loop_count: int
    character_count: int
    style_anchor_count: int
    last_narration_tick: int


@router.get("/status", response_model=TickStatusResponse)
async def get_status(runtime=Depends(_resolve_runtime)) -> TickStatusResponse:
    orch = runtime.orchestrator
    ts = runtime.tick_state
    return TickStatusResponse(
        current_tick=ts.current_tick,
        world_time=ts.world_time,
        is_paused=orch.is_paused,
        open_loop_count=ts.get_open_loop_count(),
        character_count=len(ts.list_character_states()),
        style_anchor_count=len(ts.list_style_anchors()),
        last_narration_tick=ts.last_narration_tick,
    )


@router.post("/run")
async def run_one_tick(runtime=Depends(_resolve_runtime)) -> dict:
    orch = runtime.orchestrator
    if orch.is_paused:
        raise HTTPException(
            status_code=409,
            detail="Orchestrator is paused. Call /api/tick/resume before /run.",
        )
    summary = await orch.run_tick()
    return {"ok": True, "summary": summary.model_dump(mode="json")}


@router.post("/pause")
async def pause_loop(runtime=Depends(_resolve_runtime)) -> dict:
    runtime.orchestrator.pause()
    return {"ok": True, "is_paused": True}


@router.post("/resume")
async def resume_loop(runtime=Depends(_resolve_runtime)) -> dict:
    runtime.orchestrator.resume()
    return {"ok": True, "is_paused": False}


class InjectEventRequest(BaseModel):
    id: str | None = None
    type: EventKind = Field(default="dramatic")
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    description: str
    visible_to: list[str] = Field(default_factory=list)
    narrative_value: int = Field(default=8, ge=0, le=10)


@router.post("/inject-event")
async def inject_event(
    req: InjectEventRequest, runtime=Depends(_resolve_runtime)
) -> dict:
    orch = runtime.orchestrator
    ts = runtime.tick_state

    visible_to = list(req.visible_to) or ["all_in_location"]
    if "all_in_location" in visible_to and not req.location.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "visible_to=all_in_location 需要非空 location, 否则事件对所有 "
                "CharacterAgent 都不可见 (静默被丢弃)。请显式 location 或改用 "
                "具体的 character_id 列表 / 'all'。"
            ),
        )

    candidate_id = req.id or (
        f"evt_user_{ts.current_tick}_{len(orch._injected_pending)}"
    )
    if req.id:
        existing_ids = {e.id for e in orch._injected_pending}
        if candidate_id in existing_ids:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"event id {candidate_id!r} 已在 pending 队列中, "
                    f"避免静默覆盖。请换一个 id 或省略 id 让服务端自动生成。"
                ),
            )

    event = Event(
        id=candidate_id,
        tick=ts.current_tick + 1,
        type=req.type,
        location=req.location,
        participants=req.participants,
        description=req.description,
        visible_to=visible_to,
        narrative_value=req.narrative_value,
    )
    orch.inject_event(event)
    return {"ok": True, "event": event.model_dump(mode="json")}


@router.get("/open-loops")
async def list_open_loops(
    min_urgency: int = 0,
    top_k: int = Query(50, ge=1, le=100),
    runtime=Depends(_resolve_runtime),
) -> dict:
    ts = runtime.tick_state
    loops = ts.get_open_loops(min_urgency=min_urgency, top_k=top_k)
    return {
        "count": len(loops),
        "loops": [l.model_dump(mode="json") for l in loops],
        # Phase 6-B reader sidebar — 历史累计 close 事件计数 (无 closed_loops
        # 列表, 关闭即 pop). 用于 Reader 显示 "已关 N / 当前开 M" 平衡感.
        "closed_total": ts.loops_closed_total,
    }


@router.post("/open-loops")
async def add_open_loop(
    loop: OpenLoop, runtime=Depends(_resolve_runtime)
) -> dict:
    ts = runtime.tick_state
    if ts.has_open_loop(loop.id):
        raise HTTPException(
            status_code=409,
            detail=(
                f"open_loop id {loop.id!r} 已存在, 避免覆盖累积的运行时字段 "
                f"(last_referenced_tick 等)。请先 DELETE /api/tick/open-loops/"
                f"{loop.id} 或换一个 id。"
            ),
        )
    ts.add_open_loop(loop)
    # ts.save() 是同步 JSON + os.replace, 在 async 路由里直接调会阻塞 event loop。
    await run_in_threadpool(ts.save)
    return {"ok": True, "loop": loop.model_dump(mode="json")}


@router.delete("/open-loops/{loop_id}")
async def close_open_loop(
    loop_id: str, runtime=Depends(_resolve_runtime)
) -> dict:
    ts = runtime.tick_state
    closed = ts.close_open_loop(loop_id)
    if closed is None:
        raise HTTPException(status_code=404, detail="loop not found")
    await run_in_threadpool(ts.save)
    return {"ok": True, "closed": closed.model_dump(mode="json")}


@router.get("/history")
async def get_history(
    last_n: int = Query(20, ge=1, le=500),
    runtime=Depends(_resolve_runtime),
) -> dict:
    # SQLite 查询是阻塞 IO, 在 async 路由内必须挪到线程池, 否则单慢查询会卡死整个 event loop
    rows = await run_in_threadpool(runtime.tick_db.get_recent_ticks, n=last_n)
    return {"count": len(rows), "ticks": rows}


@router.get("/event-stats")
async def get_event_stats(
    last_n_ticks: int = Query(50, ge=1, le=500),
    runtime=Depends(_resolve_runtime),
) -> dict:
    return await run_in_threadpool(
        runtime.tick_db.get_event_stats, last_n_ticks=last_n_ticks
    )


@router.get("/action-patterns")
async def get_action_patterns(
    last_n_ticks: int = Query(100, ge=1, le=500),
    runtime=Depends(_resolve_runtime),
) -> dict:
    return await run_in_threadpool(
        runtime.tick_db.get_action_patterns, last_n_ticks=last_n_ticks
    )


@router.get("/style-anchors")
async def list_style_anchors(
    top_k: int = Query(20, ge=1, le=100),
    runtime=Depends(_resolve_runtime),
) -> dict:
    ts = runtime.tick_state
    anchors = ts.get_style_anchors(top_k=top_k)
    return {
        "count": len(anchors),
        "anchors": [a.model_dump(mode="json") for a in anchors],
    }


@router.get("/character-states")
async def list_character_states(runtime=Depends(_resolve_runtime)) -> dict:
    ts = runtime.tick_state
    states = ts.list_character_states()
    return {"count": len(states), "states": [s.model_dump(mode="json") for s in states]}


@router.get("/novelty-warnings")
async def list_novelty_warnings(runtime=Depends(_resolve_runtime)) -> dict:
    ts = runtime.tick_state
    return {"warnings": ts.get_novelty_warnings()}


@router.get("/narratives")
async def list_narratives(
    start_tick: int = Query(0, ge=0),
    end_tick: int = Query(0, ge=0, description="0 = up to current tick"),
    limit: int = Query(500, ge=1, le=2000),
    runtime=Depends(_resolve_runtime),
) -> dict:
    """Phase 6-B reader API — 列出 tick 区间内的全部 narrative 正文.

    返回顺序: 按 tick 升序. 每条 ``{tick, world_time, text, char_count}``.
    ``end_tick=0`` 表示截至当前 tick. ``limit`` 防止误请整本.

    数据源: ``{data_dir}/narratives/tick_NNNNNN.txt`` (orchestrator 每 tick 写盘).
    与 ``/api/tick/history`` 的区别: history 给 TickSummary (摘要 + 元数据),
    本端点给 narrative 正文文本 — 是 reader 视图的主数据.
    """
    import os
    import re

    ts = runtime.tick_state
    current_tick = ts.get_current_tick()
    effective_end = end_tick if end_tick > 0 else current_tick

    narratives_dir = os.path.join(ts.data_dir, "narratives")

    def _read_narratives_blocking() -> list[dict]:
        if not os.path.isdir(narratives_dir):
            return []
        pat = re.compile(r"^tick_(\d{6})\.txt$")
        out: list[dict] = []
        for fname in sorted(os.listdir(narratives_dir)):
            m = pat.match(fname)
            if not m:
                continue
            tick = int(m.group(1))
            if tick < start_tick or tick > effective_end:
                continue
            path = os.path.join(narratives_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError as e:
                logger.warning("read narrative tick=%d failed: %s", tick, e)
                continue
            out.append({"tick": tick, "text": text, "char_count": len(text)})
            if len(out) >= limit:
                break
        return out

    # 整个 listdir + N 次同步 read 都跑在线程池, 防止 narratives 多 (1000+ tick)
    # 时一次请求把 event loop 卡数百 ms。
    rows = await run_in_threadpool(_read_narratives_blocking)

    return {
        "count": len(rows),
        "narratives": rows,
        "start_tick": start_tick,
        "end_tick": effective_end,
        "current_tick": current_tick,
        "truncated": len(rows) >= limit,
    }


@router.get("/diagnostic/hallucination")
async def hallucination_diagnostic(runtime=Depends(_resolve_runtime)) -> dict:
    import os

    ts = runtime.tick_state
    stats = ts.get_hallucination_stats()
    auto_degrade = os.environ.get("HALLUCINATION_AUTO_DEGRADE", "").strip()
    return {
        "stats": stats,
        "total_agents_flagged": len(stats),
        "auto_degrade_active": auto_degrade in {"1", "true", "TRUE", "yes"},
    }
