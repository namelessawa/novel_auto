"""Orchestrator P1 集成测试 - 把 EventInjector / Showrunner / NoveltyCritic /
TickDB 全部接入,验证 cadence 调度与持久化端到端。"""

from __future__ import annotations

import asyncio
import os

import pytest

from agents.character_agent import CharacterAgent
from agents.event_injector import EventInjector
from agents.narrator_agent import NarratorAgent
from agents.novelty_critic import NoveltyCritic
from agents.orchestrator import Orchestrator
from agents.showrunner import Showrunner
from agents.world_simulator import WorldSimulator
from memory.tick_state import TickState
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    TickLocation,
    WorldState,
)
from nf_core.action_resolver import ActionResolver
from persistence.tick_db import TickDB


def _world_sim_response(world_time: int, nv: int = 6) -> dict:
    return {
        "new_world_state": {
            "world_time": world_time,
            "era": "唐",
            "weather": "雨",
            "locations": [{"id": "city", "name": "都城", "type": "city"}],
            "factions": [],
        },
        "natural_events": [
            {
                "id": f"evt_nat_{world_time}",
                "tick": world_time,
                "type": "exogenous",
                "location": "city",
                "participants": [],
                "description": "雨势加大,街道泥泞",
                "visible_to": ["all_in_location"],
                "narrative_value": nv,
                "consequences": [],
            }
        ],
        "delta_summary": "雨势加大。",
    }


def _character_action_response() -> dict:
    return {
        "action_type": "speak",
        "target": "bob",
        "description": "alice 与 bob 在屋檐下对谈",
        "dialogue_spoken": "雨这么大,你为什么还要出门?",
        "dialogue_to_whom": ["bob"],
        "intent": "试探",
        "internal_monologue": "他在隐瞒什么",
        "emotional_shift": "警觉",
        "completed_goal_ids": [],
        "new_goals": [],
        "abandoned_goal_ids": [],
        "newly_learned": [],
        "newly_speculated": ["bob 与一桩旧案有关"],
        "flags": [],
    }


def _narrator_response(text: str = "雨幕之下,二人对话渐起。") -> dict:
    return {
        "narrative_text": text,
        "estimated_length": "short",
        "viewpoint_characters": ["alice"],
        "scene_focus": "雨中对话",
        "events_consumed": [],
        "open_loops_referenced": [],
        "newly_opened_loops": [],
        "style_diagnostics": {"avg_sentence_length": 12, "rhetoric_density": "low"},
        "consistency_flags": [],
    }


def _showrunner_response() -> dict:
    return {
        "pacing_assessment": {
            "current_intensity": "low",
            "recent_trend": "flat",
            "diagnosis": "节奏偏冷,缺乏戏剧火花",
        },
        "conflict_pool_status": {"count": 0, "health": "critical"},
        "cold_threads": [],
        "arc_status": [],
        "recommendations": [
            {
                "type": "trigger_dramatic_event",
                "target": "any",
                "rationale": "连续 5 tick 无高价值事件",
                "urgency": "high",
            }
        ],
    }


def _injector_response(tick: int) -> dict:
    return {
        "events": [
            {
                "id": f"evt_drama_{tick}",
                "tick": tick,
                "type": "dramatic",
                "location": "city",
                "participants": ["alice", "bob"],
                "description": "城西爆发火灾,有人在火场遗下血书",
                "visible_to": ["alice", "bob"],
                "narrative_value": 9,
                "consequences": [],
                "rationale": "Showrunner 标记过于平静",
                "predicted_consequences": ["alice 卷入调查"],
                "narrative_value_hint": 9,
            }
        ],
        "no_events_reason": None,
    }


def _novelty_response() -> dict:
    return {
        "overall_novelty_score": 6,
        "detected_patterns": [
            {
                "pattern": "alice 反复以试探作为对话开场",
                "occurrences": 3,
                "severity": "low",
                "examples": ["雨中对话", "市集对话", "屋顶对话"],
            }
        ],
        "recommendations": ["建议下次让 alice 主动暴露立场而非试探"],
    }


def _bootstrap(data_dir: str) -> TickState:
    ts = TickState(data_dir=data_dir)
    ts.set_world_state(
        WorldState(world_time=0, era="唐", locations=[TickLocation(id="city", name="都城", type="city")])
    )
    ts.upsert_character_profile(
        CharacterProfile(id="alice", name="Alice", importance_tier="A")
    )
    ts.upsert_character_profile(
        CharacterProfile(id="bob", name="Bob", importance_tier="B")
    )
    ts.upsert_character_state(
        CharacterState(
            character_id="alice",
            current_location="city",
            arc_goal="揭开旧案",
            arc_progress=0.2,
            known_facts=["十年前都城有冤案"],
        )
    )
    ts.upsert_character_state(
        CharacterState(character_id="bob", current_location="city")
    )
    return ts


def test_event_injector_triggered_when_open_loops_below_min(tmp_path, mock_llm) -> None:
    """OpenLoop 数 <3 时 Orchestrator 必须触发 EventInjector。"""
    mock_llm.set_responses(
        [
            _world_sim_response(world_time=1),
            _injector_response(tick=1),  # EventInjector 触发
            _character_action_response(),  # alice
            _character_action_response(),  # bob
            _narrator_response("血书引出旧案,雨声压过低语。"),
        ]
    )
    ts = _bootstrap(str(tmp_path))
    injector = EventInjector()
    agents = {
        "alice": CharacterAgent(ts.get_character_profile("alice")),
        "bob": CharacterAgent(ts.get_character_profile("bob")),
    }
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents=agents,
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        event_injector=injector,
        main_tracking_character_id="alice",
    )
    summary = asyncio.run(orch.run_tick())

    assert "event_injector" in summary.agents_called
    assert any(
        eid.startswith("evt_drama_") for eid in summary.events_generated
    ), summary.events_generated


def test_tick_db_persists_summary_and_events(tmp_path, mock_llm) -> None:
    """每 tick 结束 TickDB.insert_tick 写入 tick_log + events。"""
    mock_llm.set_responses(
        [
            _world_sim_response(world_time=1, nv=8),
            _character_action_response(),
            _character_action_response(),
            _narrator_response(),
        ]
    )
    ts = _bootstrap(str(tmp_path))
    tick_db = TickDB(str(tmp_path / "ticks.db"))
    agents = {
        "alice": CharacterAgent(ts.get_character_profile("alice")),
        "bob": CharacterAgent(ts.get_character_profile("bob")),
    }
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents=agents,
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        tick_db=tick_db,
        main_tracking_character_id="alice",
    )
    asyncio.run(orch.run_tick())

    rows = tick_db.get_recent_ticks(n=5)
    assert len(rows) == 1
    row = rows[0]
    assert row["tick_id"] == 1
    assert row["narrator_produced"] == 1
    assert row["narrator_chars"] > 0

    events = tick_db.get_events_in_range(from_tick=1, to_tick=1)
    assert any(e["event_type"] == "exogenous" for e in events)
    assert any(e["event_type"] == "character_action" for e in events)

    stats = tick_db.get_event_stats(last_n_ticks=10)
    assert stats["ticks_sampled"] == 1
    assert stats["by_type"].get("exogenous", 0) >= 1
    tick_db.close()


def test_showrunner_called_on_cadence_5(tmp_path, mock_llm) -> None:
    """showrunner 仅在 tick%5==0 被调用。前 4 tick 不触发。"""
    responses = []
    for t in range(1, 6):
        responses.append(_world_sim_response(world_time=t))
        if t == 5:
            # showrunner 在 tick 5 触发,排在 WorldSim 之后
            responses.append(_showrunner_response())
        # event_injector 触发(open_loops<3) - 每 tick 都会跑
        responses.append(_injector_response(tick=t))
        # 受影响角色 alice + bob
        responses.append(_character_action_response())
        responses.append(_character_action_response())
        responses.append(_narrator_response())
    mock_llm.set_responses(responses)

    ts = _bootstrap(str(tmp_path))
    agents = {
        "alice": CharacterAgent(ts.get_character_profile("alice")),
        "bob": CharacterAgent(ts.get_character_profile("bob")),
    }
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents=agents,
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        event_injector=EventInjector(),
        showrunner=Showrunner(),
        main_tracking_character_id="alice",
    )

    summaries = []
    for _ in range(5):
        summaries.append(asyncio.run(orch.run_tick()))

    # tick 1-4 不应有 showrunner
    for s in summaries[:4]:
        assert "showrunner" not in s.agents_called, f"tick {s.tick} unexpectedly called showrunner"
    # tick 5 应有
    assert "showrunner" in summaries[4].agents_called


def test_novelty_critic_writes_warnings(tmp_path, mock_llm) -> None:
    """每 20 tick NoveltyCritic 跑,recommendations 写入 TickState.novelty_warnings。"""
    # 直接构造 tick=20 的场景
    responses = []
    for t in range(1, 21):
        responses.append(_world_sim_response(world_time=t, nv=8))
        # tick 5/10/15/20 触发 showrunner
        if t % 5 == 0:
            responses.append(_showrunner_response())
        # EventInjector 每 tick(open_loops<3 持续)
        responses.append(_injector_response(tick=t))
        # alice + bob
        responses.append(_character_action_response())
        responses.append(_character_action_response())
        responses.append(_narrator_response())
        # tick 20 还要 NoveltyCritic
        if t == 20:
            responses.append(_novelty_response())
    mock_llm.set_responses(responses)

    ts = _bootstrap(str(tmp_path))
    agents = {
        "alice": CharacterAgent(ts.get_character_profile("alice")),
        "bob": CharacterAgent(ts.get_character_profile("bob")),
    }
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=WorldSimulator(),
        character_agents=agents,
        narrator=NarratorAgent(strong_model_until_tick=0),
        action_resolver=ActionResolver(),
        event_injector=EventInjector(),
        showrunner=Showrunner(),
        novelty_critic=NoveltyCritic(),
        main_tracking_character_id="alice",
    )

    final_summary = None
    for _ in range(20):
        final_summary = asyncio.run(orch.run_tick())

    assert "novelty_critic" in final_summary.agents_called
    warnings = ts.get_novelty_warnings()
    assert warnings, "expected at least one novelty warning"
    assert "alice 主动暴露立场" in warnings[0]
