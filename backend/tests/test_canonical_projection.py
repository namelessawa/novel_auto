from __future__ import annotations

from memory_system.models import (
    CharacterState,
    Event,
    OpenLoop,
    Relationship,
    TickLocation,
    WorldState,
)
from narrative.canonical_facts import CanonicalFactStore
from narrative.canonical_projection import (
    append_projection,
    project_character_epistemics,
    project_character_transition,
    project_event,
    project_guarded_continuity_state,
    project_open_loop_resolution,
    project_world_transition,
)


def _state(**updates) -> CharacterState:
    base = CharacterState(character_id="hero", current_location="outside")
    return base.model_copy(update=updates)


def test_character_transition_projects_only_accepted_differences(tmp_path) -> None:
    before = _state(
        inventory=["map", "bread"],
        status_effects=["left_shoulder_wound"],
        known_facts=["old fact"],
        money=5,
        relationships={
            "ally": Relationship(
                with_character_id="ally", type="stranger", trust=0
            )
        },
    )
    after = before.model_copy(
        update={
            "current_location": "gate",
            "inventory": ["bread", "key"],
            "status_effects": ["left_shoulder_wound", "fever"],
            "known_facts": ["old fact", "warning came from the tower"],
            "money": 3,
            "relationships": {
                "ally": Relationship(
                    with_character_id="ally", type="ally", trust=2
                )
            },
        }
    )
    projection = project_character_transition(
        before,
        after,
        tick=2,
        source_kind="state_transition",
        source_id="action:hero:2",
        source_event_ids=["evt_action"],
    )
    store = CanonicalFactStore(str(tmp_path))
    append_projection(store, projection)

    assert store.current_fact("hero", "character_location").value == {
        "state": "arrived",
        "location_id": "gate",
    }
    assert store.current_fact("item:map", "item_holder").value is None
    assert store.current_fact("item:key", "item_holder").value == "hero"
    assert store.current_fact("hero", "status_effect:fever").value is True
    # Omission is not healing: the unchanged wound creates no false update.
    assert store.current_fact("hero", "status_effect:left_shoulder_wound") is None
    known = [fact for fact in store.current_facts() if fact.predicate.startswith("character_knows:")]
    assert len(known) == 1
    assert known[0].known_by == ["hero"]
    assert store.current_fact("hero", "relationship_state:ally").value == "ally"
    assert store.current_fact("hero", "trust:ally").value == 2
    assert store.current_fact("hero", "money_balance").value == 3


def test_removed_status_is_explicit_false_not_silent_disappearance(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    injured = project_character_transition(
        _state(),
        _state(status_effects=["wound"]),
        tick=1,
        source_kind="state_transition",
        source_id="action:1",
    )
    healed = project_character_transition(
        _state(status_effects=["wound"]),
        _state(),
        tick=2,
        source_kind="state_transition",
        source_id="action:2",
    )
    append_projection(store, injured)
    append_projection(store, healed)
    assert store.current_fact("hero", "status_effect:wound").value is False


def test_event_projection_does_not_parse_free_form_consequences() -> None:
    event = Event(
        id="evt_rumor",
        tick=3,
        type="dramatic",
        description="Someone claims the king returned.",
        visible_to=["hero"],
        consequences=["the king is objectively alive"],
    )
    result = project_event(event)
    assert len(result.facts) == 1
    fact = result.facts[0]
    assert fact.predicate == "event_occurred"
    assert fact.status == "historical"
    assert fact.known_by == ["hero"]
    assert "consequences" not in fact.value


def test_speculation_is_projected_as_belief_not_objective(tmp_path) -> None:
    from memory_system.models import CharacterAction

    action = CharacterAction(
        character_id="hero",
        newly_speculated=["the guard may have torn the map"],
    )
    store = CanonicalFactStore(str(tmp_path))
    facts = append_projection(
        store,
        project_character_epistemics(
            action, tick=3, source_event_ids=["evt_action"]
        ),
    )
    assert len(facts) == 1
    assert facts[0].status == "belief"
    assert facts[0].known_by == ["hero"]
    assert facts[0] not in store.current_facts()


def test_world_transition_projects_typed_fields_only(tmp_path) -> None:
    before = WorldState(
        world_time=1,
        weather="clear",
        locations=[TickLocation(id="gate", name="Gate", current_state="open")],
    )
    after = before.model_copy(
        update={
            "world_time": 2,
            "weather": "rain",
            "locations": [
                TickLocation(id="gate", name="Gate", current_state="closed")
            ],
        }
    )
    store = CanonicalFactStore(str(tmp_path))
    append_projection(
        store,
        project_world_transition(
            before,
            after,
            tick=2,
            source_kind="world_state",
            source_id="world_simulator:2",
        ),
    )
    assert store.current_fact("world", "weather").value == "rain"
    assert store.current_fact("gate", "location_state").value == "closed"


def test_guarded_continuity_projects_schema_and_never_heals_by_omission(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    append_projection(
        store,
        project_guarded_continuity_state(
            {
                "characters": {
                    "hero": {"location": "gate", "injuries": ["left shoulder"]}
                },
                "items": {
                    "map": {"holder": "guard", "condition": "rain_damaged"}
                },
                "knowledge": [
                    {"character_id": "hero", "fact": "the bell is a warning"},
                    "an unattributed rumor",
                ],
            },
            tick=4,
            consumed_event_ids=["evt_map"],
        ),
    )
    append_projection(
        store,
        project_guarded_continuity_state(
            {"characters": {"hero": {"location": "gate"}}},
            tick=5,
        ),
    )

    assert store.current_fact("hero", "injury:left shoulder").value is True
    assert store.current_fact("item:map", "item_holder").value == "guard"
    assert store.current_fact("item:map", "item_condition").value == "rain_damaged"
    location = store.current_fact("hero", "character_location")
    assert location.valid_from_tick == 4  # unchanged tick 5 only merges evidence


def test_open_loop_resolution_retains_event_evidence() -> None:
    loop = OpenLoop(
        id="loop_map",
        opened_tick=1,
        description="Who tore the map?",
        promised_question="Who tore the map?",
    )
    result = project_open_loop_resolution(
        loop,
        tick=6,
        payoff_summary="The guard admits tearing it and loses the key.",
        evidence_event_ids=["evt_admission", "evt_key"],
    )
    fact = result.facts[0]
    assert fact.status == "historical"
    assert fact.source_event_ids == ["evt_admission", "evt_key"]
    assert fact.value["payoff_summary"].startswith("The guard")
