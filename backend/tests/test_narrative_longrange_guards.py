from __future__ import annotations

import json

from agents.narrator_agent import (
    NarratorAgent,
    NarratorOutput,
    _narrator_temperature,
)
from agents.orchestrator import Orchestrator, _select_narrator_tracking_character
from memory.tick_state import TickState
from memory_system.models import Event, OpenLoop


def test_scene_mode_and_continuity_directive_are_rendered() -> None:
    agent = NarratorAgent(enable_critic=False)
    event = Event(
        id="evt_2",
        tick=2,
        type="dramatic",
        description="承接上一段，主角已经夺回地图，现在背着伤员撤离。",
        narrative_value=8,
    )
    prompt = agent._build_user_prompt(
        tick=2,
        world_time=2,
        tracking_character_id="char_a",
        tick_events=[event],
        char_states=[],
        recent_chapter_summaries=[],
        open_loops=[],
        target_chars="600-1200 字",
        prose_tail="铁门在她身后合拢，她把地图塞进怀里。",
        reader_knowledge={
            "known_facts": [{"event_id": "evt_1", "fact": "地图已经夺回"}],
            "open_questions": [{"loop_id": "loop_a", "question": "地图缺角是谁撕的？"}],
            "recent_answers": [],
        },
        continuity_state={
            "characters": {"char_a": {"injuries": ["右肋受伤"]}},
            "items": {"地图": {"holder": "char_a", "condition": "缺角"}},
        },
    )
    assert "跨段连续性硬约束" in prompt
    assert "不得换一种说法重演" in prompt
    assert "场景模式" in prompt
    assert "travel" in prompt
    assert "读者信息边界" in prompt
    assert "不得再次当作新揭示" in prompt
    assert "叙事状态账本" in prompt
    assert "右肋受伤" in prompt
    assert "必须兑现的高价值源事件" in prompt
    assert "evt_2" in prompt


def test_ensemble_viewpoint_rotates_only_current_participants() -> None:
    event = Event(
        id="evt_group", tick=2, type="dramatic",
        description="两人从不同位置看到同一道门",
        participants=["char_a", "char_b", "unknown"],
        narrative_value=8,
    )
    kwargs = {
        "style_key": "ensemble_epic",
        "default_character_id": "char_a",
        "events": [event],
        "profile_ids": {"char_a", "char_b"},
    }
    assert _select_narrator_tracking_character(tick=1, **kwargs) == "char_a"
    assert _select_narrator_tracking_character(tick=2, **kwargs) == "char_b"
    assert _select_narrator_tracking_character(tick=3, **kwargs) == "char_a"


def test_narrator_temperature_is_conservative_and_bounded(monkeypatch) -> None:
    monkeypatch.delenv("NARRATOR_TEMPERATURE", raising=False)
    assert _narrator_temperature() == 0.65
    monkeypatch.setenv("NARRATOR_TEMPERATURE", "9")
    assert _narrator_temperature() == 1.2
    monkeypatch.setenv("NARRATOR_TEMPERATURE", "bad")
    assert _narrator_temperature() == 0.65


def test_tick_state_resolved_loop_record_persists(tmp_path) -> None:
    state = TickState(data_dir=str(tmp_path))
    state.add_open_loop(OpenLoop(
        id="loop_map",
        opened_tick=1,
        description="地图缺角隐藏了谁的名字",
        promised_question="缺角处是谁的名字？",
    ))
    state.touch_open_loop("loop_map", 2)
    state.record_reader_fact(
        event_id="evt_map", fact="林雪已经夺回地图", tick=2
    )
    state.set_narrative_continuity_state({
        "characters": {"林雪": {"location": "排水渠"}},
        "items": {"地图": {"holder": "林雪", "condition": "湿透"}},
    })
    resolved = state.resolve_open_loop(
        "loop_map",
        tick=3,
        payoff_summary="雨水显出夹层墨迹，确认名字属于林母。",
        evidence_event_ids=["evt_reveal"],
    )
    assert resolved is not None
    assert state.get_open_loop_count() == 0
    assert state.list_resolved_loop_records()[0]["reference_count"] == 1
    state.save()

    loaded = TickState(data_dir=str(tmp_path))
    assert loaded.load() is True
    records = loaded.list_resolved_loop_records()
    assert records[0]["loop_id"] == "loop_map"
    assert records[0]["evidence_event_ids"] == ["evt_reveal"]
    reader = loaded.get_reader_knowledge()
    assert reader["known_facts"][0]["event_id"] == "evt_map"
    assert reader["recent_answers"][0]["loop_id"] == "loop_map"
    continuity = loaded.get_narrative_continuity_state()
    assert continuity["items"]["地图"]["condition"] == "湿透"
    continuity["items"]["地图"]["condition"] = "完好"
    assert (
        loaded.get_narrative_continuity_state()["items"]["地图"]["condition"]
        == "湿透"
    )


def test_orchestrator_accepts_only_auditable_loop_payoff(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOOP_PAYOFF_GUARD_ENABLE", "1")
    state = TickState(data_dir=str(tmp_path))
    state.add_open_loop(OpenLoop(
        id="loop_map", opened_tick=1, description="地图缺角的秘密"
    ))
    orch = object.__new__(Orchestrator)
    orch._tick_state = state
    event = Event(
        id="evt_reveal", tick=2, type="dramatic",
        description="雨水显出夹层文字", narrative_value=8,
    )
    output = NarratorOutput(
        should_narrate=True,
        narrative_text="雨水显出夹层文字，缺角的秘密终于有了具体答案。",
        events_consumed=["evt_reveal"],
        open_loops_referenced=["loop_map"],
        resolved_open_loops=[{
            "loop_id": "loop_map",
            "payoff_summary": "夹层文字给出了缺角所藏名字与人物反应。",
            "evidence_event_ids": ["evt_reveal"],
        }],
    )
    orch._apply_narrative_loop_payoffs(output, tick=2, tick_events=[event])
    assert state.get_open_loop_count() == 0
    assert state.list_resolved_loop_records()


def test_orchestrator_rejects_loop_payoff_without_current_event(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOOP_PAYOFF_GUARD_ENABLE", "1")
    state = TickState(data_dir=str(tmp_path))
    state.add_open_loop(OpenLoop(
        id="loop_map", opened_tick=1, description="地图缺角的秘密"
    ))
    orch = object.__new__(Orchestrator)
    orch._tick_state = state
    output = NarratorOutput(
        should_narrate=True,
        narrative_text="他顺口说秘密已经解决。",
        events_consumed=[],
        open_loops_referenced=["loop_map"],
        resolved_open_loops=[{
            "loop_id": "loop_map",
            "payoff_summary": "没有事件证据却声称已经给出完整答案。",
            "evidence_event_ids": ["invented_evt"],
        }],
    )
    orch._apply_narrative_loop_payoffs(output, tick=2, tick_events=[])
    assert state.has_open_loop("loop_map")
    assert "loop_payoff_rejected:loop_map" in output.consistency_flags


def test_cjk_ellipsis_is_flagged_but_does_not_drop_narrative() -> None:
    agent = NarratorAgent(enable_critic=False)
    event = Event(
        id="evt_pause", tick=4, type="dramatic",
        description="门后传来断续回答", narrative_value=7,
    )
    text = "我贴住门板听着。" + "里面响了一下……我没有出声。" * 6
    out = agent._parse_output(
        json.dumps({
            "narrative_text": text,
            "events_consumed": ["evt_pause"],
            "newly_opened_loops": [],
        }, ensure_ascii=False),
        "medium",
        4,
        [event],
    )
    assert out.should_narrate is True
    assert out.narrative_text == text
    assert "excessive_cjk_ellipsis" in out.consistency_flags


def test_new_loop_accepts_schema_aliases_and_question_as_description() -> None:
    agent = NarratorAgent(enable_critic=False)
    event = Event(
        id="evt_map", tick=2, type="dramatic",
        description="地图夹层显出半个名字", narrative_value=8,
    )
    out = agent._parse_output(
        json.dumps({
            "narrative_text": "雨水渗进地图夹层，半个从未见过的名字慢慢浮出来。",
            "events_consumed": ["evt_map"],
            "newly_opened_loops": [{
                "loop_id": "loop_name",
                "loop_type": "mystery",
                "promised_question": "夹层里的名字属于谁？",
                "payoff_requirements": ["揭示完整名字", "让林雪作出反应"],
                "origin_event_ids": ["evt_map"],
            }],
            "continuity_state": {
                "characters": {"林雪": {"location": "泵房"}},
                "items": {"地图": {"holder": "林雪", "condition": "湿透"}},
            },
        }, ensure_ascii=False),
        "medium",
        2,
        [event],
    )
    assert len(out.newly_opened_loops) == 1
    loop = out.newly_opened_loops[0]
    assert loop.id == "loop_name"
    assert loop.type == "mystery"
    assert loop.description == "夹层里的名字属于谁？"
    assert out.continuity_state["items"]["地图"]["condition"] == "湿透"
