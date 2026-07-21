"""Phase 7 CanonicalFact sidecar and minimum fact-chain counterexamples."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from narrative.canonical_facts import (
    CanonicalFact,
    CanonicalFactConflictError,
    CanonicalFactStore,
    FactSourceRef,
    OutOfOrderFactError,
    build_canonical_fact,
    canonical_fact_id,
)


def _event(event_id: str, tick: int) -> FactSourceRef:
    return FactSourceRef(
        kind="event_consequence", source_id=event_id, tick=tick
    )


def _fact(
    subject: str,
    predicate: str,
    value: object,
    tick: int,
    *,
    status: str = "active",
    source: FactSourceRef | None = None,
    known_by: tuple[str, ...] = (),
) -> CanonicalFact:
    return build_canonical_fact(
        subject_id=subject,
        predicate=predicate,
        value=value,
        valid_from_tick=tick,
        source_refs=[source or _event(f"evt_{tick}", tick)],
        known_by=known_by,
        status=status,  # type: ignore[arg-type]
    )


def test_map_transfer_supersedes_old_holder(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    protagonist = store.append(_fact("map", "item_holder", "hero", 1))
    gatekeeper = store.append(_fact("map", "item_holder", "gatekeeper", 2))

    assert store.current_fact("map", "item_holder") == gatekeeper
    assert store.get(protagonist.fact_id).status == "superseded"
    assert store.get(protagonist.fact_id).valid_until_tick == 2
    assert gatekeeper.supersedes_fact_id == protagonist.fact_id


def test_damaged_map_is_not_restored_by_historical_summary(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    store.append(_fact("map", "item_condition", "intact", 1))
    damaged = store.append(_fact("map", "item_condition", "rain_damaged", 2))
    summary = _fact(
        "map",
        "item_condition",
        "intact",
        1,
        status="historical",
        source=FactSourceRef(kind="summary", source_id="node_l2", tick=20),
    )
    store.append(summary)

    assert store.current_fact("map", "item_condition") == damaged


def test_moving_to_city_gate_is_not_projected_as_arrived(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    moving = store.append(
        _fact(
            "hero",
            "character_location",
            {"state": "moving_to", "destination_id": "city_gate"},
            3,
        )
    )

    current = store.current_fact("hero", "character_location")
    assert current == moving
    assert current.value["state"] == "moving_to"
    assert current.value.get("location_id") is None


def test_unmentioned_injury_remains_active(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    injury = store.append(
        _fact("hero", "injury:left_shoulder", "wounded", 4)
    )
    store.append(
        _fact(
            "scene_5",
            "narrative_omits",
            "hero_injury",
            5,
            status="historical",
            source=FactSourceRef(kind="summary", source_id="scene_5", tick=5),
        )
    )

    assert store.current_fact("hero", "injury:left_shoulder") == injury


def test_rumor_does_not_upgrade_to_objective_known_fact(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    rumor = store.append(
        _fact(
            "warning_source",
            "identity",
            "captain",
            6,
            status="rumor",
            known_by=("hero",),
        )
    )

    assert store.current_fact("warning_source", "identity") is None
    assert rumor in store.facts_known_by("hero")
    assert rumor not in store.facts_known_by("hero", include_subjective=False)


def test_character_lie_does_not_overwrite_objective_fact(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    objective = store.append(_fact("map", "item_holder", "gatekeeper", 7))
    lie = store.append(
        _fact(
            "map",
            "item_holder",
            "hero",
            8,
            status="belief",
            known_by=("listener",),
        )
    )

    assert store.current_fact("map", "item_holder") == objective
    assert lie.status == "belief"


def test_new_active_fact_requires_authoritative_source() -> None:
    with pytest.raises(ValidationError, match="authoritative source"):
        build_canonical_fact(
            subject_id="map",
            predicate="item_holder",
            value="hero",
            valid_from_tick=9,
            source_refs=[
                FactSourceRef(kind="summary", source_id="summary_9", tick=9)
            ],
        )


def test_superseded_fact_is_not_returned_as_current(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    old = store.append(_fact("hero", "alive_status", "alive", 1))
    dead = store.append(
        build_canonical_fact(
            subject_id="hero",
            predicate="alive_status",
            value="dead",
            valid_from_tick=10,
            source_event_ids=["evt_death"],
            reversible=False,
        )
    )

    assert store.get(old.fact_id).status == "superseded"
    assert store.current_fact("hero", "alive_status") == dead


def test_summary_cannot_overwrite_current_canonical_fact(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    current = store.append(_fact("hero", "character_location", "outside", 11))
    with pytest.raises(ValidationError, match="authoritative source"):
        store.append(
            _fact(
                "hero",
                "character_location",
                "inside",
                2,
                source=FactSourceRef(
                    kind="summary", source_id="old_chapter", tick=2
                ),
            )
        )
    assert store.current_fact("hero", "character_location") == current


def test_legend_never_enters_character_known_facts_as_objective(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    legend = store.append(
        _fact(
            "old_king",
            "returned_from_death",
            True,
            12,
            status="rumor",
            source=FactSourceRef(kind="legend", source_id="legend_12", tick=12),
            known_by=("hero",),
        )
    )

    assert legend in store.facts_known_by("hero")
    assert store.current_fact("old_king", "returned_from_death") is None


def test_fact_id_is_stable_across_source_order() -> None:
    kwargs = {
        "subject_id": "map",
        "predicate": "item_condition",
        "value": {"damage": "rain", "usable": False},
        "valid_from_tick": 13,
    }
    assert canonical_fact_id(**kwargs) == canonical_fact_id(**kwargs)
    a = build_canonical_fact(
        **kwargs,
        source_event_ids=["evt_b", "evt_a"],
        known_by=["bob", "alice"],
    )
    b = build_canonical_fact(
        **kwargs,
        source_event_ids=["evt_a", "evt_b"],
        known_by=["alice", "bob"],
    )
    assert a == b


def test_replayed_fact_merges_provenance_idempotently(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    first = build_canonical_fact(
        subject_id="map",
        predicate="item_holder",
        value="gatekeeper",
        valid_from_tick=14,
        source_event_ids=["evt_transfer"],
    )
    second = build_canonical_fact(
        subject_id="map",
        predicate="item_holder",
        value="gatekeeper",
        valid_from_tick=14,
        source_narrative_ticks=[14],
        known_by=["hero"],
    )
    store.append(first)
    merged = store.append(second)

    assert store.size == 1
    assert merged.source_event_ids == ["evt_transfer"]
    assert merged.source_narrative_ticks == [14]
    assert merged.known_by == ["hero"]


def test_out_of_order_update_cannot_replace_newer_current_fact(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    store.append(_fact("hero", "character_location", "city", 20))
    with pytest.raises(OutOfOrderFactError):
        store.append(_fact("hero", "character_location", "gate", 19))


def test_atomic_persistence_round_trip_and_missing_old_data(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    assert store.load() is False
    current = store.append(_fact("map", "item_quantity", 1, 21))
    store.append(
        _fact(
            "map",
            "item_location",
            "archive",
            1,
            status="historical",
            source=FactSourceRef(kind="summary", source_id="summary_1", tick=1),
        )
    )
    store.save()

    payload = json.loads((tmp_path / "canonical_facts.json").read_text("utf-8"))
    assert payload["version"] == 1
    restored = CanonicalFactStore(str(tmp_path))
    assert restored.load() is True
    assert restored.current_fact("map", "item_quantity") == current
    assert restored.size == 2


def test_same_fact_id_with_different_semantics_is_rejected(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    first = _fact("map", "item_holder", "hero", 22)
    store.append(first)
    collision = first.model_copy(update={"value": "gatekeeper"})
    with pytest.raises(CanonicalFactConflictError):
        store.append(collision)

