from __future__ import annotations

from memory_system.models import CharacterState, Relationship
from narrative.canonical_facts import CanonicalFactStore
from narrative.canonical_projection import append_projection, project_guarded_continuity_state
from narrative.canonical_reconciliation import (
    reconcile_all,
    reconcile_continuity_state,
    reconcile_fact_ledger,
    reconcile_knowledge_graph,
    reconcile_tick_state,
)
from narrative.fact_ledger import Fact


def _active(
    store: CanonicalFactStore,
    subject: str,
    predicate: str,
    value: object,
) -> None:
    append_projection(
        store,
        project_guarded_continuity_state(
            (
                {"characters": {subject: {"location": value}}}
                if predicate == "character_location"
                else {"items": {subject.removeprefix("item:"): {"holder": value}}}
            ),
            tick=1,
            consumed_event_ids=["evt_1"],
        ),
    )


def test_tick_state_reports_holder_mismatch_without_mutation(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    _active(store, "item:map", "item_holder", "guard")
    hero = CharacterState(character_id="hero", inventory=["map"])
    guard = CharacterState(character_id="guard", inventory=[])

    report = reconcile_tick_state(store, [hero, guard])
    assert report.hard_conflict_count == 1
    assert report.issues[0].expected == "guard"
    assert report.issues[0].actual == "hero"
    assert hero.inventory == ["map"]


def test_moving_to_is_not_compared_as_arrived(tmp_path) -> None:
    from narrative.canonical_facts import build_canonical_fact

    store = CanonicalFactStore(str(tmp_path))
    store.append(
        build_canonical_fact(
            subject_id="hero",
            predicate="character_location",
            value={"state": "moving_to", "destination_id": "gate"},
            valid_from_tick=1,
            source_event_ids=["evt_move"],
        )
    )
    report = reconcile_tick_state(
        store, [CharacterState(character_id="hero", current_location="road")]
    )
    assert report.hard_conflict_count == 0
    assert report.skipped == 1


def test_legacy_fact_ledger_mismatch_is_auditable(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    _active(store, "hero", "character_location", "inside")
    old = Fact(
        id="legacy_location",
        kind="location",
        subject="hero",
        predicate="outside",
        established_tick=1,
        status="active",
    )
    report = reconcile_fact_ledger(store, [old])
    assert report.hard_conflict_count == 1
    assert report.issues[0].view == "fact_ledger"


def test_knowledge_graph_location_match_and_gap_are_separate(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    _active(store, "hero", "character_location", "inside")
    graph = {
        "entities": [{"id": "hero"}],
        "relations": [
            {"source": "hero", "target": "inside", "relation_type": "located_at"}
        ],
    }
    matched = reconcile_knowledge_graph(store, graph)
    assert matched.matched == 1
    missing = reconcile_knowledge_graph(store, {"entities": [], "relations": []})
    assert missing.hard_conflict_count == 0
    assert len(missing.coverage_gaps) == 1


def test_continuity_omission_does_not_invalidate_injury(tmp_path) -> None:
    from narrative.canonical_facts import build_canonical_fact

    store = CanonicalFactStore(str(tmp_path))
    injury = build_canonical_fact(
        subject_id="hero",
        predicate="injury:left shoulder",
        value=True,
        valid_from_tick=1,
        source_event_ids=["evt_injury"],
    )
    store.append(injury)
    report = reconcile_continuity_state(
        store, {"characters": {"hero": {"location": "gate"}}}
    )
    assert report.hard_conflict_count == 0
    assert store.current_fact("hero", "injury:left shoulder") == injury


def test_reconcile_all_keeps_coverage_and_conflicts_distinct(tmp_path) -> None:
    store = CanonicalFactStore(str(tmp_path))
    _active(store, "hero", "character_location", "inside")
    state = CharacterState(
        character_id="hero",
        current_location="outside",
        relationships={
            "ally": Relationship(with_character_id="ally", type="ally", trust=2)
        },
    )
    report = reconcile_all(
        store,
        character_states=[state],
        legacy_facts=[],
        knowledge_graph={"entities": [], "relations": []},
        continuity_state={},
    )
    payload = report.to_dict()
    assert payload["hard_conflict_count"] == 1
    assert payload["coverage_gap_count"] == 1
    assert payload["by_view"]["tick_state"]["hard_conflicts"] == 1

