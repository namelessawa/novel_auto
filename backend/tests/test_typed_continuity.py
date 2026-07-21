from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from memory.tick_state import TickState
from narrative.typed_continuity import (
    TypedContinuityState,
    continuity_legacy_view,
    normalise_continuity_state,
)


CATALOGS = {
    "valid_character_ids": {"char_hero", "char_linxue"},
    "valid_location_ids": {"city_gate_inner", "city_interior"},
    "valid_item_ids": {"item_map", "item_satchel"},
    "valid_fact_ids": {"fact_secret"},
    "valid_open_loop_ids": {"loop_gate"},
    "valid_event_ids": {"evt_gate"},
}


def _valid_payload() -> dict:
    return {
        "schema_version": "1",
        "time_marker": "tick:12",
        "characters": {
            "char_hero": {
                "character_id": "char_hero",
                "location_id": "city_gate_inner",
                "movement_status": "arrived",
                "destination_location_id": None,
                "alive_status": "alive",
                "injuries": [
                    {
                        "injury_id": "injury_left_leg",
                        "body_part": "left_leg",
                        "severity": "moderate",
                        "status": "treated",
                        "source_event_id": "evt_gate",
                    }
                ],
                "supporting_character_ids": ["char_linxue"],
                "carried_by_character_id": None,
                "knowledge_fact_ids": ["fact_secret"],
            },
            "char_linxue": {
                "character_id": "char_linxue",
                "location_id": "city_gate_inner",
                "movement_status": "arrived",
                "alive_status": "alive",
            },
        },
        "items": {
            "item_map": {
                "item_id": "item_map",
                "holder_character_ids": ["char_hero"],
                "location_id": None,
                "quantity": 1,
                "condition": "damaged",
                "container_item_id": "item_satchel",
            }
        },
        "newly_known_fact_ids": {"char_hero": ["fact_secret"]},
        "active_open_loop_ids": ["loop_gate"],
    }


def test_typed_continuity_round_trips_and_validates_references() -> None:
    result = normalise_continuity_state(_valid_payload(), **CATALOGS)

    assert result.source_schema == "typed_v1"
    assert result.references_checked is True
    assert result.authoritative_eligible is True
    assert result.issues == []
    assert json.loads(result.typed_state.model_dump_json()) == (
        TypedContinuityState.model_validate(_valid_payload()).model_dump(mode="json")
    )
    assert result.raw_payload == _valid_payload()


def test_typed_location_rejects_action_or_support_phrase() -> None:
    payload = _valid_payload()
    payload["characters"]["char_hero"]["location_id"] = "由林雪架着"

    with pytest.raises(ValidationError):
        TypedContinuityState.model_validate(payload)

    result = normalise_continuity_state(payload, **CATALOGS)
    assert result.source_schema == "invalid"
    assert result.authoritative_eligible is False
    assert result.typed_state.characters == {}
    assert result.raw_payload["characters"]["char_hero"]["location_id"] == "由林雪架着"


def test_support_relation_is_separate_from_location() -> None:
    state = TypedContinuityState.model_validate(_valid_payload())
    hero = state.characters["char_hero"]

    assert hero.location_id == "city_gate_inner"
    assert hero.movement_status == "arrived"
    assert hero.supporting_character_ids == ["char_linxue"]
    assert hero.carried_by_character_id is None


def test_legacy_natural_language_location_falls_back_without_guessing() -> None:
    legacy = {
        "characters": {
            "char_hero": {
                "location": "由林雪架着",
                "status": "存活，受伤",
                "injuries": ["左腿流血"],
                "supporting_character_ids": ["char_linxue"],
            }
        },
        "items": {
            "地图": {"holder": "他", "condition": "被雨淋湿"},
        },
        "knowledge": ["他听说城门已经关闭"],
        "time_marker": "入夜后",
    }

    result = normalise_continuity_state(legacy, **CATALOGS)

    assert result.source_schema == "legacy"
    assert result.authoritative_eligible is False
    assert result.raw_payload == legacy
    hero = result.typed_state.characters["char_hero"]
    assert hero.location_id is None
    assert hero.movement_status == "unknown"
    assert hero.alive_status == "unknown"
    assert hero.injuries == []
    assert hero.supporting_character_ids == ["char_linxue"]
    assert result.typed_state.items == {}
    assert len(result.issues) >= 4


def test_legacy_stable_ids_are_copied_but_never_marked_authoritative() -> None:
    legacy = {
        "characters": {
            "char_hero": {
                "location": "city_gate_inner",
                "movement_status": "arrived",
                "alive_status": "alive",
            }
        },
        "items": {
            "item_map": {
                "holder": "char_hero",
                "quantity": 1,
                "condition": "damaged",
            }
        },
    }

    result = normalise_continuity_state(legacy, **CATALOGS)

    assert result.typed_state.characters["char_hero"].location_id == "city_gate_inner"
    assert result.typed_state.items["item_map"].holder_character_ids == ["char_hero"]
    assert result.authoritative_eligible is False


def test_unknown_typed_reference_is_valid_shape_but_not_authoritative() -> None:
    payload = _valid_payload()
    payload["characters"]["char_hero"]["location_id"] = "outer_fortification"

    result = normalise_continuity_state(payload, **CATALOGS)

    assert result.source_schema == "typed_v1"
    assert result.typed_state.characters["char_hero"].location_id == "outer_fortification"
    assert result.authoritative_eligible is False
    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("unknown_location_id", "characters.char_hero.location_id")
    ]


def test_reference_catalogs_are_required_for_authoritative_eligibility() -> None:
    result = normalise_continuity_state(_valid_payload())

    assert result.source_schema == "typed_v1"
    assert result.references_checked is False
    assert result.authoritative_eligible is False
    assert result.issues == []


def test_invalid_legacy_payload_is_json_safe_and_non_fatal() -> None:
    result = normalise_continuity_state(["not", {"a": object()}])

    assert result.source_schema == "invalid"
    assert result.authoritative_eligible is False
    assert result.typed_state == TypedContinuityState()
    json.dumps(result.raw_payload, ensure_ascii=False)


def test_non_finite_raw_value_is_retained_as_json_safe_audit_data() -> None:
    result = normalise_continuity_state(
        {"schema_version": "1", "items": {"item_map": {"quantity": float("nan")}}}
    )

    assert result.source_schema == "invalid"
    assert result.raw_payload["items"]["item_map"]["quantity"] == "nan"
    json.dumps(result.raw_payload, ensure_ascii=False, allow_nan=False)


def test_injury_source_event_must_exist_in_reference_catalog() -> None:
    payload = _valid_payload()
    payload["characters"]["char_hero"]["injuries"][0]["source_event_id"] = (
        "evt_unknown"
    )

    result = normalise_continuity_state(payload, **CATALOGS)

    assert result.authoritative_eligible is False
    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("unknown_event_id", "characters.char_hero.injuries.0.source_event_id")
    ]


def test_quantity_does_not_coerce_string_or_boolean() -> None:
    for invalid in ("1", True, -1, float("inf")):
        payload = _valid_payload()
        payload["items"]["item_map"]["quantity"] = invalid
        with pytest.raises(ValidationError):
            TypedContinuityState.model_validate(payload)


def test_location_movement_states_are_not_equivalent() -> None:
    departing = _valid_payload()
    departing["characters"]["char_hero"].update(
        {
            "location_id": "city_gate_inner",
            "movement_status": "departing",
            "destination_location_id": "city_interior",
        }
    )
    arrived = _valid_payload()
    arrived["characters"]["char_hero"].update(
        {
            "location_id": "city_interior",
            "movement_status": "arrived",
            "destination_location_id": None,
        }
    )

    first = TypedContinuityState.model_validate(departing)
    second = TypedContinuityState.model_validate(arrived)
    assert first.characters["char_hero"] != second.characters["char_hero"]


def test_legacy_view_omits_in_transit_location_and_unknown_values() -> None:
    payload = _valid_payload()
    payload["characters"]["char_hero"].update(
        {
            "movement_status": "in_transit",
            "destination_location_id": "city_interior",
            "alive_status": "unknown",
        }
    )
    payload["items"]["item_map"].update(
        {
            "holder_character_ids": ["char_hero", "char_linxue"],
            "condition": "unknown",
        }
    )

    view = continuity_legacy_view(payload)

    assert "location" not in view["characters"]["char_hero"]
    assert "alive_status" not in view["characters"]["char_hero"]
    assert view["characters"]["char_hero"]["destination_location_id"] == (
        "city_interior"
    )
    assert "holder" not in view["items"]["item_map"]
    assert view["items"]["item_map"]["holder_character_ids"] == [
        "char_hero",
        "char_linxue",
    ]
    assert "condition" not in view["items"]["item_map"]


def test_legacy_view_does_not_reinterpret_legacy_payload() -> None:
    legacy = {"characters": {"char_hero": {"location": "由林雪架着"}}}

    assert continuity_legacy_view(legacy) == legacy


def test_tick_state_persists_typed_state_and_raw_audit(tmp_path) -> None:
    normalized = normalise_continuity_state(_valid_payload(), **CATALOGS)
    state = TickState(str(tmp_path))
    state.set_narrative_continuity_state(
        normalized.typed_state.model_dump(mode="json"),
        audit=normalized.model_dump(mode="json"),
    )
    state.save()

    restored = TickState(str(tmp_path))
    assert restored.load() is True
    assert restored.get_narrative_continuity_state()["schema_version"] == "1"
    audit = restored.get_narrative_continuity_audit()
    assert audit["source_schema"] == "typed_v1"
    assert audit["authoritative_eligible"] is True
    assert audit["raw_payload"] == _valid_payload()
    audit["raw_payload"].clear()
    assert restored.get_narrative_continuity_audit()["raw_payload"]
