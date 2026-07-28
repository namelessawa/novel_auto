from __future__ import annotations

from story.models import (
    CanonicalState,
    ContextManifest,
    MemoryCanonicalClaim,
    MemoryRecord,
    MemoryRepositoryState,
)
from story.persistence import MemoryRepository
from story.semantic_recall import (
    SemanticRecallValidator,
    recorded_semantic_recall_probes,
)


def _state() -> CanonicalState:
    return CanonicalState(
        revision=31,
        world={
            "location_rules": {"lighthouse": "地下室禁止明火"},
        },
        character_knowledge={
            "shen_yan": ["不知道旧信末页的落款"],
        },
        relationships={
            "shen_yan:lin_qiu": {
                "description": "共同维护灯塔的多年搭档",
            }
        },
        items={"letter": {"holder": "lin_qiu"}},
        canonical_facts={
            "promise": {"status": "open"},
            "main_clue": {"status": "open"},
        },
    )


def _manifest(selected_ids: list[str]) -> ContextManifest:
    return ContextManifest(
        novel_id="recall",
        section_id="section_0030",
        story_bible_revision=1,
        canonical_state_revision=30,
        selected_memory_ids=selected_ids,
        total_chars=100,
        total_token_estimate=50,
    )


def test_all_seven_recorded_semantic_recall_categories_pass() -> None:
    probes = recorded_semantic_recall_probes()
    selected = [
        memory_id
        for probe in probes
        for memory_id in probe.required_memory_ids
    ]
    narrative = "。".join(
        phrase
        for probe in probes
        for phrase in probe.required_prose
    )
    validator = SemanticRecallValidator()

    results = [
        validator.validate(
            probe,
            manifest=_manifest(selected),
            narrative_text=narrative,
            final_state=_state(),
        )
        for probe in probes
    ]

    assert len(results) == 7
    assert {result.category for result in results} == {
        "knowledge_boundary",
        "relationship",
        "item",
        "location_rule",
        "promise",
        "main_thread",
        "stale_fact",
    }
    assert all(result.accepted for result in results)


def test_selected_memory_without_prose_semantics_fails() -> None:
    probe = recorded_semantic_recall_probes()[0]
    result = SemanticRecallValidator().validate(
        probe,
        manifest=_manifest(probe.required_memory_ids),
        narrative_text="这里只记录了 memory ID，没有正确回忆事实。",
        final_state=_state(),
    )

    assert result.accepted is False
    assert "SELECTED_MEMORY_NOT_USED_IN_PROSE" in result.violation_codes


def test_stale_or_conflicting_memories_are_audited_and_filtered(tmp_path) -> None:
    repository = MemoryRepository(str(tmp_path))
    repository.save(
        MemoryRepositoryState(
            records={
                "current": MemoryRecord(
                    id="current",
                    summary="旧信由林秋保管",
                    entities=["lin_qiu"],
                    importance=10,
                    canonical_claims=[
                        MemoryCanonicalClaim(
                            path="/items/letter/holder",
                            expected="lin_qiu",
                        )
                    ],
                    created_at_revision=2,
                ),
                "conflict": MemoryRecord(
                    id="conflict",
                    summary="旧信仍由沈砚保管",
                    entities=["lin_qiu"],
                    importance=10,
                    canonical_claims=[
                        MemoryCanonicalClaim(
                            path="/items/letter/holder",
                            expected="shen_yan",
                        )
                    ],
                    created_at_revision=1,
                ),
                "superseded": MemoryRecord(
                    id="superseded",
                    summary="旧版本",
                    entities=["lin_qiu"],
                    canon_status="superseded",
                    importance=10,
                    created_at_revision=1,
                ),
                "future": MemoryRecord(
                    id="future",
                    summary="未来版本",
                    entities=["lin_qiu"],
                    importance=10,
                    created_at_revision=99,
                ),
            }
        )
    )

    result = repository.select_relevant(
        {"lin_qiu"},
        set(),
        canonical_state=_state(),
        canonical_revision=31,
        limit=12,
    )

    assert [item.id for item in result.selected] == ["current"]
    discarded = {item.memory_id: item for item in result.discarded}
    assert discarded["conflict"].reason == "canonical_conflict"
    assert discarded["conflict"].conflicting_paths == ["/items/letter/holder"]
    assert discarded["superseded"].reason == "canon_status_superseded"
    assert discarded["future"].reason == "future_canonical_revision"
