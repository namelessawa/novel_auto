"""iter#103 — orchestrator 真正调 tick_state.close_open_loop 落地测试.

Phase 2 §closed=0 leakage: 跨 130 tick × 3 seed bench 全 0 自动关闭.
此测试保证 Showrunner 输出的 loops_to_close 真正落到 TickState 上.
"""

from __future__ import annotations

import asyncio

import pytest

from agents.character_agent import CharacterAgent
from agents.event_injector import EventInjector
from agents.narrator_agent import NarratorAgent
from agents.orchestrator import Orchestrator
from agents.showrunner import Showrunner
from agents.world_simulator import WorldSimulator
from memory.tick_state import TickState
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    OpenLoop,
    TickLocation,
    WorldState,
)
from nf_core.action_resolver import ActionResolver


def _world_sim_response(world_time: int) -> dict:
    return {
        "world_time_delta": 1,
        "weather_change": None,
        "scheduled_events_due": [],
        "natural_events": [],
        "ambient_state": {"time_of_day": "noon"},
    }


def _showrunner_response(loops_to_close: list[str]) -> dict:
    return {
        "pacing_assessment": {"current_intensity": "high", "recent_trend": "rising",
                              "diagnosis": "open_loops 已 >= 6, 触发关闭"},
        "conflict_pool_status": {"count": 6, "health": "low"},
        "cold_threads": [],
        "arc_status": [],
        "recommendations": [],
        "loops_to_close": loops_to_close,
    }


def _character_action_response() -> dict:
    return {
        "intent": "observe",
        "action_type": "observe",
        "target_location": "city",
        "target_character_id": None,
        "rationale": "了解状况",
        "dialogue": None,
        "emotional_state": "neutral",
    }


def _narrator_response(text: str = "test narration") -> dict:
    return {
        "decision": "narrate",
        "narration": text,
        "length_tier": "S",
        "events_consumed": [],
        "open_loops_referenced": [],
        "newly_opened_loops": [],
        "style_diagnostics": {"avg_sentence_length": 12, "rhetoric_density": "low"},
        "consistency_flags": [],
    }


def _bootstrap_with_loops(tmp_path) -> TickState:
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(
        WorldState(
            world_time=0, era="唐",
            locations=[TickLocation(id="city", name="都城", type="city")],
        )
    )
    ts.upsert_character_profile(
        CharacterProfile(id="alice", name="Alice", importance_tier="A")
    )
    ts.upsert_character_state(
        CharacterState(character_id="alice", current_location="city")
    )
    # 6 个 open_loops, 模拟 iter#102 bench 末态
    for i in range(6):
        ts.add_open_loop(
            OpenLoop(
                id=f"loop_{i}", opened_tick=0,
                description=f"open loop #{i}", urgency=5,
                type="mystery", last_referenced_tick=0,
            )
        )
    return ts


def _build_responses_5_ticks(loops_to_close: list[str]) -> list[dict]:
    """组装跑 5 tick 所需的所有 LLM responses.

    重要: 在 6 open_loops + 单 alice 的最小 setup 中, 每 tick 实际只 LLM 调用
    world_simulator (character/narrator 早返回, 因无事件触发). tick 5 额外
    showrunner. 总 6 calls.
    """
    responses = []
    for t in range(1, 6):
        responses.append(_world_sim_response(world_time=t))
        if t == 5:
            responses.append(_showrunner_response(loops_to_close=loops_to_close))
    return responses


def test_showrunner_close_loops_actually_drains_pool(tmp_path, mock_llm) -> None:
    """Showrunner 输出 loops_to_close 后, tick_state.get_open_loops()
    必须真正少了对应条数."""
    mock_llm.set_responses(_build_responses_5_ticks(["loop_0", "loop_3"]))
    ts = _bootstrap_with_loops(tmp_path)
    assert len(ts.get_open_loops()) == 6

    agents = {"alice": CharacterAgent(ts.get_character_profile("alice"))}
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents=agents,
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        showrunner=Showrunner(),
        event_injector=EventInjector(),
    )

    # 跑到 tick 5 触发 Showrunner. tick 1-4 不该 close (cadence=5)
    for _ in range(5):
        asyncio.run(orch.run_tick())

    # 关键断言: loop_0 / loop_3 已不在池中
    remaining_ids = {l.id for l in ts.get_open_loops()}
    assert "loop_0" not in remaining_ids, "loop_0 必须被 Showrunner 关闭"
    assert "loop_3" not in remaining_ids, "loop_3 必须被 Showrunner 关闭"
    # 其余 4 个不该动
    assert remaining_ids == {"loop_1", "loop_2", "loop_4", "loop_5"}


def test_showrunner_close_ignores_unknown_ids(tmp_path, mock_llm) -> None:
    """LLM 偶尔输出不存在的 ID, orchestrator 必须 silently ignore."""
    mock_llm.set_responses(
        _build_responses_5_ticks(["loop_NONEXISTENT", "loop_1"])
    )
    ts = _bootstrap_with_loops(tmp_path)

    agents = {"alice": CharacterAgent(ts.get_character_profile("alice"))}
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents=agents,
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        showrunner=Showrunner(),
        event_injector=EventInjector(),
    )
    for _ in range(5):
        asyncio.run(orch.run_tick())

    remaining_ids = {l.id for l in ts.get_open_loops()}
    # loop_1 关闭, 不存在 ID 静默忽略 → 不抛
    assert "loop_1" not in remaining_ids
    assert len(remaining_ids) == 5


def test_showrunner_empty_close_list_keeps_pool(tmp_path, mock_llm) -> None:
    """Showrunner 不推荐关闭 → 池子完整保留."""
    mock_llm.set_responses(_build_responses_5_ticks([]))
    ts = _bootstrap_with_loops(tmp_path)
    agents = {"alice": CharacterAgent(ts.get_character_profile("alice"))}
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents=agents,
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        showrunner=Showrunner(),
        event_injector=EventInjector(),
    )
    for _ in range(5):
        asyncio.run(orch.run_tick())
    assert len(ts.get_open_loops()) == 6


def test_showrunner_assess_raises_pool_unchanged(tmp_path, mock_llm) -> None:
    """iter#106 review MEDIUM gap: Showrunner.assess 抛错时池子必须不变.

    orchestrator 的 try/except 已包住 assess + close 全段, 但缺测试保证
    pool 不被偶尔写入. 这是 fail-safe invariant.
    """
    # 故意只给 5 个 world_sim, 让 tick 5 的 showrunner JSON 拿不到, 解析失败
    # → ShowrunnerOutput() 空状态, loops_to_close=[], 但 assess 不抛.
    # 真正抛错: 用一个拒绝调用的 Showrunner mock.
    class _BrokenShowrunner:
        async def assess(self, **kwargs):
            raise RuntimeError("LLM provider exploded")

    # 注: 不需要 mock_llm 队列, 因为 broken showrunner 在 tick 5 直接抛
    # world_sim 仍走真实 LLM mock
    mock_llm.set_responses([
        _world_sim_response(world_time=1),
        _world_sim_response(world_time=2),
        _world_sim_response(world_time=3),
        _world_sim_response(world_time=4),
        _world_sim_response(world_time=5),
    ])
    ts = _bootstrap_with_loops(tmp_path)
    agents = {"alice": CharacterAgent(ts.get_character_profile("alice"))}
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents=agents,
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        showrunner=_BrokenShowrunner(),
        event_injector=EventInjector(),
    )
    for _ in range(5):
        asyncio.run(orch.run_tick())
    # 关键 invariant: 池子状态不变
    assert len(ts.get_open_loops()) == 6
    assert {l.id for l in ts.get_open_loops()} == {f"loop_{i}" for i in range(6)}
