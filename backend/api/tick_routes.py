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

from memory_system.models import Event, EventKind, OpenLoop

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
    # v2.19.1 — 用 EventKind Literal 在 FastAPI 边界就拒非法值 (422 而非 500)。
    # 此前 plain str 让 Event(type=...) 内部 Pydantic 校验失败时, 用户收到 500 +
    # 内部模型路径泄露 traceback。
    type: EventKind = Field(default="dramatic")
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    description: str
    visible_to: list[str] = Field(default_factory=list)
    narrative_value: int = Field(default=8, ge=0, le=10)


@router.post("/inject-event")
async def inject_event(req: InjectEventRequest) -> dict:
    orch = _require_orchestrator()
    ts = _require_tick_state()

    # v2.19.1 — 计算最终 visible_to (含空 → all_in_location 的 fallback), 然后
    # 校验"all_in_location 必须有 location" 这一硬约束。否则事件对所有人不可见,
    # 调用方拿 200 但事件被静默忽略 — 比 500 更难调试。
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

    # v2.19.1 — id 冲突检查。当前只校验 _injected_pending 范围 (即将被下一 tick
    # 消费的批次), 这是冲突最常见的发生窗口。跨 tick 的历史 id 由 TickDB 唯一
    # 约束兜底, 此处不重复扫 SQLite。
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
        tick=ts.current_tick + 1,  # 注入到下一个 tick
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


@router.get("/diagnostic/hallucination")
async def hallucination_diagnostic() -> dict:
    """v2.18 Phase 9 — Guardian 幻觉率 + AgentRuntimeState 监控数据。

    返回每个被 Guardian 建议过降级的 agent 的统计 (degrade_recommendations /
    hallucination_hits / last_degrade_recommended_tick / model_tier_override_active),
    以及全局 HALLUCINATION_AUTO_DEGRADE 开关状态。

    生产用法:
    * shadow 期 (auto_degrade_active=False): 监控真阳率, 数据 N 天后再决定开关
    * active 期 (auto_degrade_active=True): 实时观察 model_tier_override 命中分布
    """
    import os

    ts = _require_tick_state()
    stats = ts.get_hallucination_stats()
    auto_degrade = os.environ.get("HALLUCINATION_AUTO_DEGRADE", "").strip()
    return {
        "stats": stats,
        "total_agents_flagged": len(stats),
        "auto_degrade_active": auto_degrade in {"1", "true", "TRUE", "yes"},
    }
