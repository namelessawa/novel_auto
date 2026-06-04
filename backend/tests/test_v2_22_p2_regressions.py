"""v2.22 P2 修复回归套件 — Orchestrator 注入事件在 tick 失败时不丢失。

此前 _run_tick_unlocked 在阶段 2 末尾就 self._injected_pending.clear(); 之后任何
阶段抛错 (asyncio.gather return_exceptions=False, narrative_writer I/O, ...)
都会让用户手工注入的事件永久丢失, 无法重试。

现在: 仅在 tick 完整跑完 + 落盘后才用 id 集合差从队列移除。
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from agents.character_agent import CharacterAgent
from agents.narrator_agent import NarratorAgent
from agents.orchestrator import Orchestrator
from agents.world_simulator import WorldSimulator
from memory.tick_state import TickState
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    Event,
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
                {
                    "id": "city",
                    "name": "都城",
                    "type": "city",
                    "present_characters": [],
                }
            ],
            "factions": [],
            "active_global_events": [],
            "world_rules": [],
        },
        "natural_events": [],
        "delta_summary": "时间向前。",
    }


def _narrator_response(text: str) -> dict:
    return {
        "narrative_text": text,
        "estimated_length": "short",
        "viewpoint_characters": ["alice"],
        "scene_focus": "scene",
        "events_consumed": [],
        "open_loops_referenced": [],
        "newly_opened_loops": [],
        "style_diagnostics": {},
        "consistency_flags": [],
    }


def _character_action_response() -> dict:
    return {
        "action_type": "speak",
        "target": "self",
        "description": "alice 自言自语",
        "dialogue_spoken": "...",
        "dialogue_to_whom": [],
        "intent": "思考",
        "internal_monologue": "...",
        "emotional_shift": "平静",
        "completed_goal_ids": [],
        "new_goals": [],
        "abandoned_goal_ids": [],
        "newly_learned": [],
        "newly_speculated": [],
        "flags": [],
    }


def _bootstrap_state(data_dir: str) -> TickState:
    ts = TickState(data_dir=data_dir)
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
            age=28,
            role="主角",
            importance_tier="A",
        )
    )
    ts.upsert_character_state(
        CharacterState(character_id="alice", current_location="city")
    )
    return ts


def _build_orch(ts: TickState) -> Orchestrator:
    return Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents={"alice": CharacterAgent(ts.get_character_profile("alice"))},
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        main_tracking_character_id="alice",
    )


def _make_injected_event(ev_id: str = "evt_user_test_0") -> Event:
    return Event(
        id=ev_id,
        tick=0,
        type="exogenous",
        location="city",
        participants=["alice"],
        description="用户手工注入: 城外狼烟四起",
        visible_to=["alice"],
        narrative_value=8,
        consequences=[],
    )


def test_injected_event_consumed_on_successful_tick(tmp_path, mock_llm) -> None:
    """成功 tick 后, 注入队列里对应 id 的事件应被移除 (正常路径不回归)。"""
    mock_llm.set_responses(
        [
            _world_sim_response(world_time=1),
            _character_action_response(),
            _narrator_response("狼烟逼近, alice 不敢动。"),
        ]
    )

    ts = _bootstrap_state(str(tmp_path))
    orch = _build_orch(ts)
    evt = _make_injected_event()
    orch.inject_event(evt)
    assert len(orch._injected_pending) == 1

    summary = asyncio.run(orch.run_tick())

    assert summary.tick == 1
    # 注入 id 应出现在 events_generated 里
    assert evt.id in summary.events_generated
    # 注入队列消费完毕
    assert orch._injected_pending == [], (
        f"成功 tick 后注入队列必须清空; 实际剩 {[e.id for e in orch._injected_pending]}"
    )


def test_injected_event_preserved_when_tick_fails(tmp_path, mock_llm) -> None:
    """tick 中途异常时, 注入事件必须留在队列里供下 tick 重试 — 这是 P2 核心修复。

    此前 .clear() 在阶段 2 末就执行, 阶段 3-7 抛错就永久丢失。
    """
    mock_llm.set_responses([_world_sim_response(world_time=1)])

    ts = _bootstrap_state(str(tmp_path))
    orch = _build_orch(ts)
    evt = _make_injected_event("evt_user_test_fail")
    orch.inject_event(evt)
    assert len(orch._injected_pending) == 1

    # 把阶段 5b 的 memory 写入强行炸掉, 模拟 tick 中段崩溃
    with patch.object(
        orch,
        "_ingest_events_to_memory",
        side_effect=RuntimeError("simulated mid-tick failure"),
    ):
        with pytest.raises(RuntimeError, match="simulated mid-tick failure"):
            asyncio.run(orch.run_tick())

    # 关键断言: 事件没被消费, 仍在队列里
    assert len(orch._injected_pending) == 1, (
        "tick 失败时注入事件必须保留供重试; "
        f"实际队列状态: {[e.id for e in orch._injected_pending]}"
    )
    assert orch._injected_pending[0].id == evt.id


def test_concurrent_inject_during_tick_preserved(tmp_path, mock_llm) -> None:
    """tick 期间通过 inject_event 新追加的事件 (不同 id) 不应被本 tick 误消费。

    虽然 _tick_lock 保护 run_tick, inject_event 本身不加锁, HTTP 线程理论上
    可在 tick 中段 append。新事件 id 不在 injected_event_ids 集合里, 应保留。
    """
    mock_llm.set_responses(
        [
            _world_sim_response(world_time=1),
            _character_action_response(),
            _narrator_response("alice 收到密报。"),
        ]
    )

    ts = _bootstrap_state(str(tmp_path))
    orch = _build_orch(ts)
    initial_evt = _make_injected_event("evt_initial")
    orch.inject_event(initial_evt)

    # 在 narrator 阶段附近偷偷 append 一个新事件, 模拟外部并发注入
    original_narrate = orch._narrate

    async def _spy_narrate(tick, events):
        # 模拟外部 HTTP 线程在 tick 中段插入新事件
        orch.inject_event(_make_injected_event("evt_late"))
        return await original_narrate(tick, events)

    orch._narrate = _spy_narrate

    summary = asyncio.run(orch.run_tick())

    # initial 应被消费, late 应保留供下 tick
    remaining_ids = {e.id for e in orch._injected_pending}
    assert "evt_initial" not in remaining_ids, (
        "本 tick 注入的事件 (snapshot 时已在队列) 必须被消费"
    )
    assert "evt_late" in remaining_ids, (
        "tick 期间新追加的事件不应被误消费; "
        f"实际剩余: {remaining_ids}"
    )
    assert initial_evt.id in summary.events_generated
