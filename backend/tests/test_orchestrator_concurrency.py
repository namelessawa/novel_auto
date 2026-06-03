"""Orchestrator 并发与暂停语义测试 (v2.15)。

覆盖两个 P0 修复:
1. ``run_tick`` 用 ``asyncio.Lock`` 串行化 — 并发调用不会双写 tick_state。
2. ``/api/tick/run`` 在 ``orch.is_paused`` 时返回 409 — pause() 真正阻止手动 /run。
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from agents.character_agent import CharacterAgent
from agents.narrator_agent import NarratorAgent
from agents.orchestrator import Orchestrator
from agents.world_simulator import WorldSimulator
from api.tick_routes import (
    _container,
    pause_loop,
    resume_loop,
    run_one_tick,
    set_orchestrator_dependencies,
)
from memory.tick_state import TickState
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    TickLocation,
    WorldState,
)
from nf_core.action_resolver import ActionResolver


def _world_sim_response(world_time: int) -> dict:
    return {
        "new_world_state": {
            "world_time": world_time,
            "era": "战国",
            "current_season": "秋",
            "weather": "晴",
            "locations": [
                {"id": "city", "name": "都城", "type": "city", "present_characters": []}
            ],
            "factions": [],
            "active_global_events": [],
            "world_rules": [],
        },
        "natural_events": [],
        "delta_summary": "稳态推进。",
    }


def _bootstrap(tmp_path) -> tuple[TickState, Orchestrator]:
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(
        WorldState(
            world_time=0,
            era="战国",
            locations=[TickLocation(id="city", name="都城", type="city")],
        )
    )
    ts.upsert_character_profile(
        CharacterProfile(
            id="alice",
            name="Alice",
            role="主角",
            importance_tier="A",
        )
    )
    ts.upsert_character_state(
        CharacterState(character_id="alice", current_location="city")
    )
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents={"alice": CharacterAgent(ts.get_character_profile("alice"))},
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        main_tracking_character_id="alice",
    )
    return ts, orch


def test_run_tick_serializes_concurrent_calls(tmp_path, mock_llm) -> None:
    """两个 run_tick 并发触发 → tick 必须串行推进, current_tick 增量恰为 2。"""
    # 给两轮 tick 准备无 character_action / 无 narrator 的最小响应链
    mock_llm.set_responses(
        [
            _world_sim_response(world_time=1),
            _world_sim_response(world_time=2),
        ]
    )
    ts, orch = _bootstrap(tmp_path)
    assert ts.current_tick == 0

    async def _run_both() -> tuple:
        return await asyncio.gather(orch.run_tick(), orch.run_tick())

    s1, s2 = asyncio.run(_run_both())

    # tick_state 实际推进 2 步, 不多不少
    assert ts.current_tick == 2
    # 两个 summary tick 编号必须不同 — 如果未串行化, 两次 advance_tick 会竞态
    assert {s1.tick, s2.tick} == {1, 2}


def test_paused_route_rejects_manual_run(tmp_path, mock_llm) -> None:
    """pause() 后调用 /api/tick/run 必须返回 409, 不推进 tick。"""
    ts, orch = _bootstrap(tmp_path)
    set_orchestrator_dependencies(orchestrator=orch, tick_state=ts)

    async def _scenario() -> None:
        await pause_loop()
        assert orch.is_paused is True
        with pytest.raises(HTTPException) as exc:
            await run_one_tick()
        assert exc.value.status_code == 409
        # 验证 tick 没有推进
        assert ts.current_tick == 0
        # resume 后恢复能跑
        await resume_loop()
        mock_llm.set_responses([_world_sim_response(world_time=1)])
        res = await run_one_tick()
        assert res["ok"] is True
        assert ts.current_tick == 1

    asyncio.run(_scenario())

    # 清理 — set_orchestrator_dependencies 不接受 None, 直接清容器避免污染其他测试
    _container.orchestrator = None
    _container.tick_state = None
    _container.tick_db = None
