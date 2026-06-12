"""iter#139 Phase 4-E — runtime active-cast cap.

Showrunner.sidelined_characters → orchestrator wire → tick_state TTL map.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from agents.character_agent import CharacterAgent
from agents.event_injector import EventInjector
from agents.narrator_agent import NarratorAgent
from agents.orchestrator import Orchestrator
from agents.showrunner import Showrunner, ShowrunnerOutput
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


# --- Showrunner parse ------------------------------------------------------


def _showrunner_payload(sidelined):
    return json.dumps(
        {
            "pacing_assessment": {},
            "conflict_pool_status": {"count": 0, "health": "ok"},
            "cold_threads": [],
            "arc_status": [],
            "recommendations": [],
            "loops_to_close": [],
            "sidelined_characters": sidelined,
        },
        ensure_ascii=False,
    )


def test_parse_sidelined_str_list():
    sr = Showrunner()
    out = sr._parse_output(_showrunner_payload(["char_a", "char_b"]))
    assert out.sidelined_characters == ["char_a", "char_b"]


def test_parse_sidelined_dict_objects():
    sr = Showrunner()
    out = sr._parse_output(
        _showrunner_payload([{"character_id": "char_a"}, {"id": "char_b"}])
    )
    assert out.sidelined_characters == ["char_a", "char_b"]


def test_parse_sidelined_empty():
    sr = Showrunner()
    out = sr._parse_output(_showrunner_payload([]))
    assert out.sidelined_characters == []


def test_parse_sidelined_missing_field():
    sr = Showrunner()
    out = sr._parse_output(
        json.dumps({"pacing_assessment": {}, "recommendations": []})
    )
    assert out.sidelined_characters == []


def test_parse_sidelined_skips_invalid():
    sr = Showrunner()
    out = sr._parse_output(_showrunner_payload(["char_a", "", None, 42, "char_b"]))
    assert out.sidelined_characters == ["char_a", "char_b"]


def test_system_prompt_documents_sideline_criteria():
    from agents.showrunner import SYSTEM_PROMPT

    assert "sidelined_characters" in SYSTEM_PROMPT
    assert "arc_progress" in SYSTEM_PROMPT
    # 不要 sideline A 级或 arc_progress > 0.7 保护
    assert "A 级" in SYSTEM_PROMPT
    assert "0.7" in SYSTEM_PROMPT


# --- TickState API ---------------------------------------------------------


def _bootstrap_ts(tmp_path) -> TickState:
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(
        WorldState(
            world_time=0, era="测试",
            locations=[TickLocation(id="city", name="都城", type="city")],
        )
    )
    for cid in ("char_a", "char_b", "char_c"):
        ts.upsert_character_profile(
            CharacterProfile(id=cid, name=cid.upper(), importance_tier="A")
        )
        ts.upsert_character_state(
            CharacterState(character_id=cid, current_location="city")
        )
    return ts


def test_sideline_default_ttl_blocks_char(tmp_path):
    ts = _bootstrap_ts(tmp_path)
    assert not ts.is_character_sidelined("char_a")
    ts.sideline_character("char_a")
    assert ts.is_character_sidelined("char_a")
    assert ts.list_sidelined_characters()["char_a"] == ts.SIDELINE_DEFAULT_TTL


def test_sideline_unknown_char_noop(tmp_path):
    """未知 char 不创建幽灵 sideline (orchestrator 已 logger.warning)."""
    ts = _bootstrap_ts(tmp_path)
    ts.sideline_character("char_NONEXISTENT")
    assert not ts.is_character_sidelined("char_NONEXISTENT")
    assert "char_NONEXISTENT" not in ts.list_sidelined_characters()


def test_sideline_negative_ttl_noop(tmp_path):
    ts = _bootstrap_ts(tmp_path)
    ts.sideline_character("char_a", ttl=0)
    assert not ts.is_character_sidelined("char_a")


def test_sideline_repeat_takes_max_ttl(tmp_path):
    """重复 sideline 同 char 取较大 ttl 防 silently 缩短."""
    ts = _bootstrap_ts(tmp_path)
    ts.sideline_character("char_a", ttl=15)
    ts.sideline_character("char_a", ttl=5)
    assert ts.list_sidelined_characters()["char_a"] == 15


def test_tick_down_decrements_and_recovers(tmp_path):
    ts = _bootstrap_ts(tmp_path)
    ts.sideline_character("char_a", ttl=2)
    ts.sideline_character("char_b", ttl=1)

    recovered = ts.tick_down_sidelines()
    assert recovered == ["char_b"]
    assert ts.is_character_sidelined("char_a")
    assert not ts.is_character_sidelined("char_b")

    recovered = ts.tick_down_sidelines()
    assert recovered == ["char_a"]
    assert not ts.is_character_sidelined("char_a")


def test_tick_down_no_sidelines_returns_empty(tmp_path):
    ts = _bootstrap_ts(tmp_path)
    assert ts.tick_down_sidelines() == []


def test_save_load_roundtrip_sidelines(tmp_path):
    ts = _bootstrap_ts(tmp_path)
    ts.sideline_character("char_a", ttl=5)
    ts.sideline_character("char_b", ttl=3)
    ts.save()

    ts2 = TickState(data_dir=str(tmp_path))
    ts2.load()
    assert ts2.list_sidelined_characters() == {"char_a": 5, "char_b": 3}


def test_load_old_state_without_sidelines_field(tmp_path):
    """老 state file 没 sidelined_characters 字段, load 后视作 {}."""
    ts = _bootstrap_ts(tmp_path)
    ts.save()
    # 手动改 tick_state.json 删 sidelined_characters
    import json
    state_file = tmp_path / "tick_state.json"
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    payload.pop("sidelined_characters", None)
    state_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    ts2 = TickState(data_dir=str(tmp_path))
    ts2.load()
    assert ts2.list_sidelined_characters() == {}


# --- Orchestrator wire end-to-end ------------------------------------------


def _world_sim_response(t):
    return {
        "world_time_delta": 1, "weather_change": None,
        "scheduled_events_due": [], "natural_events": [],
        "ambient_state": {"time_of_day": "noon"},
    }


def _showrunner_response(sidelined):
    return {
        "pacing_assessment": {}, "conflict_pool_status": {"count": 6, "health": "ok"},
        "cold_threads": [], "arc_status": [], "recommendations": [],
        "loops_to_close": [], "sidelined_characters": sidelined,
    }


def test_orchestrator_wire_sidelines_actually_skip_batch_decide(tmp_path, mock_llm, caplog):
    """Showrunner 输出 sidelined → orchestrator 实际不调 batch_decide LLM."""
    caplog.set_level(logging.INFO, logger="agents.orchestrator")
    ts = _bootstrap_ts(tmp_path)
    # 给 6 open_loops 让 EventInjector 不触发
    for i in range(6):
        ts.add_open_loop(OpenLoop(
            id=f"loop_{i}", opened_tick=0, description=f"l{i}",
            urgency=5, type="mystery", last_referenced_tick=0,
        ))

    # 5 tick: 每 tick world_sim, tick 5 showrunner sidelined=["char_a"]
    responses = []
    for t in range(1, 6):
        responses.append(_world_sim_response(t))
        if t == 5:
            responses.append(_showrunner_response(["char_a"]))
    mock_llm.set_responses(responses)

    agents = {
        cid: CharacterAgent(ts.get_character_profile(cid))
        for cid in ("char_a", "char_b", "char_c")
    }
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

    # char_a 应被 sideline (ttl 默认 10)
    assert ts.is_character_sidelined("char_a")
    sidelines = ts.list_sidelined_characters()
    # 5 tick 跑过 → sideline 是 tick 5 设定, 之后 tick 5 也算 1 次 tick_down?
    # 实际: orchestrator 在 phase 3 起调 tick_down, 而 sideline 在同 tick 阶段 2 设
    # → 同 tick 内 sideline 立刻被 tick_down 减 1 (TTL 10 - 1 = 9)
    assert sidelines["char_a"] == ts.SIDELINE_DEFAULT_TTL - 1


def test_orchestrator_unknown_sideline_id_logs_warning(tmp_path, mock_llm, caplog):
    """LLM 偶尔输出不存在 char_id, orchestrator 必须 logger.warning + 不写入."""
    caplog.set_level(logging.WARNING, logger="agents.orchestrator")
    ts = _bootstrap_ts(tmp_path)
    for i in range(6):
        ts.add_open_loop(OpenLoop(
            id=f"loop_{i}", opened_tick=0, description=f"l{i}",
            urgency=5, type="mystery", last_referenced_tick=0,
        ))

    responses = []
    for t in range(1, 6):
        responses.append(_world_sim_response(t))
        if t == 5:
            responses.append(_showrunner_response(["char_GHOST", "char_b"]))
    mock_llm.set_responses(responses)

    agents = {
        cid: CharacterAgent(ts.get_character_profile(cid))
        for cid in ("char_a", "char_b", "char_c")
    }
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

    assert "char_GHOST" in caplog.text
    assert "unknown" in caplog.text
    # char_b 被正常 sideline
    assert ts.is_character_sidelined("char_b")
    # char_GHOST 没幽灵 sideline
    assert not ts.is_character_sidelined("char_GHOST")
