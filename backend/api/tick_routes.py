"""tick_routes — FastAPI 路由,暴露 Orchestrator 的 tick 控制与诊断 API。

| Method | Path                          | 用途                                  |
|--------|-------------------------------|---------------------------------------|
| GET    | /api/tick/status              | 当前 tick / 暂停态 / OpenLoop 数      |
| POST   | /api/tick/run                 | 同步执行 1 个 tick(管理员手动)        |
| POST   | /api/tick/pause               | 暂停后续自动循环                       |
| POST   | /api/tick/resume              | 恢复                                  |
| POST   | /api/tick/inject-event        | 手动注入 Event                        |
| GET    | /api/tick/open-loops          | 当前所有开放伏笔                       |
| GET    | /api/tick/history             | 最近 N 个 TickSummary (来自 TickDB)   |
| GET    | /api/tick/event-stats         | Showrunner 视角的事件统计              |
| GET    | /api/tick/style-anchors       | 已注册的风格锚点                       |
| GET    | /api/tick/character-states    | 全部 CharacterState                   |

注: 路由不在此模块中实例化 Orchestrator - main.py 启动时把全局实例注入到
``set_orchestrator_dependencies()``,这样测试可以无依赖注入 mock。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from memory_system.models import Event, OpenLoop

logger = logging.getLogger(__name__)


# --- 依赖注入容器 -----------------------------------------------------------


class _OrchestratorContainer:
    """Orchestrator + TickState + TickDB 的延迟绑定容器。"""

    def __init__(self) -> None:
        self.orchestrator: Any | None = None
        self.tick_state: Any | None = None
        self.tick_db: Any | None = None


_container = _OrchestratorContainer()


def set_orchestrator_dependencies(
    *,
    orchestrator: Any | None = None,
    tick_state: Any | None = None,
    tick_db: Any | None = None,
) -> None:
    """main.py 启动时调用,把全局实例注入路由层。"""
    if orchestrator is not None:
        _container.orchestrator = orchestrator
    if tick_state is not None:
        _container.tick_state = tick_state
    if tick_db is not None:
        _container.tick_db = tick_db


def _require_orchestrator():
    if _container.orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="Orchestrator not initialized. Call set_orchestrator_dependencies() first.",
        )
    return _container.orchestrator


def _require_tick_state():
    if _container.tick_state is None:
        raise HTTPException(status_code=503, detail="TickState not initialized.")
    return _container.tick_state


# --- 路由定义 ---------------------------------------------------------------


router = APIRouter(prefix="/api/tick", tags=["tick"])


class TickStatusResponse(BaseModel):
    current_tick: int
    world_time: int
    is_paused: bool
    open_loop_count: int
    character_count: int
    style_anchor_count: int
    last_narration_tick: int


@router.get("/status", response_model=TickStatusResponse)
async def get_status() -> TickStatusResponse:
    orch = _require_orchestrator()
    ts = _require_tick_state()
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
async def run_one_tick() -> dict:
    orch = _require_orchestrator()
    if orch.is_paused:
        # v2.15 — pause() 必须真正阻止手动 /run; 否则 start_loop 暂停后用户仍可
        # 通过 /run 推进 tick, 破坏暂停语义。
        raise HTTPException(
            status_code=409,
            detail="Orchestrator is paused. Call /api/tick/resume before /run.",
        )
    summary = await orch.run_tick()
    return {"ok": True, "summary": summary.model_dump(mode="json")}


@router.post("/pause")
async def pause_loop() -> dict:
    orch = _require_orchestrator()
    orch.pause()
    return {"ok": True, "is_paused": True}


@router.post("/resume")
async def resume_loop() -> dict:
    orch = _require_orchestrator()
    orch.resume()
    return {"ok": True, "is_paused": False}


class InjectEventRequest(BaseModel):
    id: str | None = None
    type: str = Field(default="dramatic")
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    description: str
    visible_to: list[str] = Field(default_factory=list)
    narrative_value: int = Field(default=8, ge=0, le=10)


@router.post("/inject-event")
async def inject_event(req: InjectEventRequest) -> dict:
    orch = _require_orchestrator()
    ts = _require_tick_state()
    event = Event(
        id=req.id or f"evt_user_{ts.current_tick}_{len(orch._injected_pending)}",
        tick=ts.current_tick + 1,  # 注入到下一个 tick
        type=req.type,  # type: ignore[arg-type]
        location=req.location,
        participants=req.participants,
        description=req.description,
        visible_to=req.visible_to or ["all_in_location"],
        narrative_value=req.narrative_value,
    )
    orch.inject_event(event)
    return {"ok": True, "event": event.model_dump(mode="json")}


@router.get("/open-loops")
async def list_open_loops(min_urgency: int = 0, top_k: int = 50) -> dict:
    ts = _require_tick_state()
    loops = ts.get_open_loops(min_urgency=min_urgency, top_k=top_k)
    return {"count": len(loops), "loops": [l.model_dump(mode="json") for l in loops]}


@router.post("/open-loops")
async def add_open_loop(loop: OpenLoop) -> dict:
    """管理员手动新增 OpenLoop。"""
    ts = _require_tick_state()
    ts.add_open_loop(loop)
    ts.save()
    return {"ok": True, "loop": loop.model_dump(mode="json")}


@router.delete("/open-loops/{loop_id}")
async def close_open_loop(loop_id: str) -> dict:
    ts = _require_tick_state()
    closed = ts.close_open_loop(loop_id)
    if closed is None:
        raise HTTPException(status_code=404, detail="loop not found")
    ts.save()
    return {"ok": True, "closed": closed.model_dump(mode="json")}


@router.get("/history")
async def get_history(last_n: int = 20) -> dict:
    if _container.tick_db is None:
        raise HTTPException(status_code=503, detail="TickDB not initialized.")
    rows = _container.tick_db.get_recent_ticks(n=last_n)
    return {"count": len(rows), "ticks": rows}


@router.get("/event-stats")
async def get_event_stats(last_n_ticks: int = 50) -> dict:
    if _container.tick_db is None:
        raise HTTPException(status_code=503, detail="TickDB not initialized.")
    return _container.tick_db.get_event_stats(last_n_ticks=last_n_ticks)


@router.get("/action-patterns")
async def get_action_patterns(last_n_ticks: int = 100) -> dict:
    if _container.tick_db is None:
        raise HTTPException(status_code=503, detail="TickDB not initialized.")
    return _container.tick_db.get_action_patterns(last_n_ticks=last_n_ticks)


@router.get("/style-anchors")
async def list_style_anchors(top_k: int = 20) -> dict:
    ts = _require_tick_state()
    anchors = ts.get_style_anchors(top_k=top_k)
    return {"count": len(anchors), "anchors": [a.model_dump(mode="json") for a in anchors]}


@router.get("/character-states")
async def list_character_states() -> dict:
    ts = _require_tick_state()
    states = ts.list_character_states()
    return {"count": len(states), "states": [s.model_dump(mode="json") for s in states]}


@router.get("/novelty-warnings")
async def list_novelty_warnings() -> dict:
    ts = _require_tick_state()
    return {"warnings": ts.get_novelty_warnings()}
