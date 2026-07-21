from __future__ import annotations

import json

from agents.narrator_agent import NARRATOR_SYSTEM_PROMPT, NarratorAgent
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    Event,
    TickLocation,
    WorldState,
)
from narrative.typed_continuity import continuity_legacy_view


def _event() -> Event:
    return Event(
        id="evt_gate",
        tick=1,
        type="dramatic",
        location="city_gate_inner",
        participants=["char_hero"],
        description="主角越过城门并收好地图。",
        consequences=["主角抵达城门内侧", "地图仍由主角持有"],
        narrative_value=8,
    )


def _catalogs() -> dict[str, set[str]]:
    return {
        "valid_character_ids": {"char_hero", "char_ally"},
        "valid_location_ids": {"city_gate_inner", "city_gate_outer"},
        "valid_item_ids": {"item_map"},
        "valid_fact_ids": set(),
        "valid_open_loop_ids": set(),
        "valid_event_ids": {"evt_gate"},
    }


def _typed_state() -> dict:
    return {
        "schema_version": "1",
        "time_marker": "tick:1",
        "characters": {
            "char_hero": {
                "character_id": "char_hero",
                "location_id": "city_gate_inner",
                "movement_status": "arrived",
                "destination_location_id": None,
                "alive_status": "alive",
                "injuries": [],
                "supporting_character_ids": ["char_ally"],
                "carried_by_character_id": None,
                "knowledge_fact_ids": [],
            }
        },
        "items": {
            "item_map": {
                "item_id": "item_map",
                "holder_character_ids": ["char_hero"],
                "location_id": None,
                "quantity": 1,
                "condition": "damaged",
                "container_item_id": None,
            }
        },
        "newly_known_fact_ids": {},
        "active_open_loop_ids": [],
    }


def _raw_response(continuity_state: dict) -> str:
    return json.dumps(
        {
            "narrative_text": (
                "门轴在身后合拢。主角把沾水的地图压进内袋，"
                "同伴扶住他的肩，两人停在城门内侧确认追兵没有跟上。"
            ),
            "events_consumed": ["evt_gate"],
            "newly_opened_loops": [],
            "continuity_state": continuity_state,
        },
        ensure_ascii=False,
    )


def test_narrator_parses_valid_typed_ledger_and_retains_raw_audit() -> None:
    out = NarratorAgent(enable_critic=False)._parse_output(
        _raw_response(_typed_state()),
        "medium",
        1,
        [_event()],
        continuity_catalogs=_catalogs(),
    )

    assert out.should_narrate is True
    assert out.continuity_state["schema_version"] == "1"
    assert out.continuity_state_audit["source_schema"] == "typed_v1"
    assert out.continuity_state_audit["authoritative_eligible"] is True
    assert out.continuity_state_audit["raw_payload"] == _typed_state()
    assert "continuity_state_legacy_fallback" not in out.consistency_flags
    assert continuity_legacy_view(
        out.continuity_state, audit=out.continuity_state_audit
    )["characters"]["char_hero"]["location"] == "city_gate_inner"


def test_narrator_keeps_legacy_output_and_marks_non_authoritative_fallback() -> None:
    legacy = {
        "characters": {"char_hero": {"location": "city_gate_inner"}},
        "items": {"item_map": {"holder": "char_hero"}},
    }
    out = NarratorAgent(enable_critic=False)._parse_output(
        _raw_response(legacy),
        "medium",
        1,
        [_event()],
        continuity_catalogs=_catalogs(),
    )

    assert out.continuity_state == legacy
    assert out.continuity_state_audit["source_schema"] == "legacy"
    assert out.continuity_state_audit["authoritative_eligible"] is False
    assert "continuity_state_legacy_fallback" in out.consistency_flags


def test_unknown_typed_reference_is_not_exposed_to_legacy_consumers() -> None:
    typed = _typed_state()
    typed["characters"]["char_hero"]["location_id"] = "invented_location"
    out = NarratorAgent(enable_critic=False)._parse_output(
        _raw_response(typed),
        "medium",
        1,
        [_event()],
        continuity_catalogs=_catalogs(),
    )

    assert out.continuity_state_audit["authoritative_eligible"] is False
    assert "continuity_state_reference_invalid" in out.consistency_flags
    assert continuity_legacy_view(
        out.continuity_state, audit=out.continuity_state_audit
    ) == {}


def test_narrator_prompt_lists_only_context_ids_and_typed_schema() -> None:
    agent = NarratorAgent(enable_critic=False)
    prompt = agent._build_user_prompt(
        tick=1,
        world_time=1,
        tracking_character_id="char_hero",
        tick_events=[_event()],
        char_states=[
            CharacterState(
                character_id="char_hero",
                current_location="city_gate_outer",
                inventory=["item_map"],
            )
        ],
        recent_chapter_summaries=[],
        open_loops=[],
        target_chars="300-700 字",
        char_profiles={
            "char_hero": CharacterProfile(id="char_hero", name="林雪")
        },
        world_state=WorldState(
            locations=[
                TickLocation(id="city_gate_inner", name="城门内侧"),
                TickLocation(id="city_gate_outer", name="城门外侧"),
            ]
        ),
        continuity_catalogs=_catalogs(),
    )

    assert "Typed continuity_state v1" in prompt
    assert "city_gate_inner" in prompt
    assert "item_map" in prompt
    assert "invented_location" not in prompt
    assert "supporting_character_ids" in prompt
    assert '"schema_version": "1"' in NARRATOR_SYSTEM_PROMPT
