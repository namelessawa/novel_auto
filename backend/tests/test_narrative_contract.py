from __future__ import annotations

from story.models import CanonicalState, SectionGoal, StoryBible, StoryThread
from story.narrative_contract import (
    LengthConstraint,
    NarrativeContractBuilder,
    NarrativeContractInput,
    RequiredEvent,
)


def test_builder_is_deterministic_and_revision_bound() -> None:
    bible = StoryBible(
        revision=3,
        premise="旧港真相等待公开。",
        theme="责任",
        setting_summary="无超自然力量的旧港。",
    )
    state = CanonicalState(
        revision=7,
        world={"locations": [{"id": "tower", "name": "灯塔"}]},
        characters={"shen": {"name": "沈砚"}, "lin": {"name": "林秋"}},
        items={"letter": {"name": "旧信", "owners": ["shen"]}},
        relationships={"shen:lin": {"description": "多年搭档"}},
    )
    goal = SectionGoal(
        section_id="ch0001_s0002",
        objective="沈砚把旧信交给林秋。",
        viewpoint_character_id="shen",
        involved_characters=["shen", "lin"],
        narrative_constraints=NarrativeContractInput(
            required_events=[
                RequiredEvent(id="handover", actor="shen", action="交信", target="lin")
            ],
            length_constraint=LengthConstraint(min_chars=300, max_chars=600),
        ),
    )
    thread = StoryThread(id="truth", description="旧信真相", status="open")
    builder = NarrativeContractBuilder()

    first = builder.build(
        story_bible=bible,
        canonical_state=state,
        section_goal=goal,
        story_threads=[thread],
    )
    second = builder.build(
        story_bible=bible,
        canonical_state=state,
        section_goal=goal,
        story_threads=[thread],
    )

    assert first == second
    assert first.contract_hash == second.contract_hash
    assert first.story_bible_revision == 3
    assert first.canonical_state_revision == 7
    assert first.style_priority == "subordinate_to_facts"
    assert [item.id for item in first.allowed_entities.characters] == ["lin", "shen"]
    assert first.allowed_entities.locations[0].name == "灯塔"
    assert first.allowed_entities.items[0].name == "旧信"
    assert first.required_events[0].id == "handover"
    assert first.protected_relationships[0].relationship == "多年搭档"
    assert first.length_constraint == LengthConstraint(min_chars=300, max_chars=600)


def test_builder_uses_section_goal_when_no_explicit_event() -> None:
    contract = NarrativeContractBuilder().build(
        story_bible=StoryBible(
            premise="选择",
            theme="诚实",
            setting_summary="旧城",
        ),
        canonical_state=CanonicalState(characters={"a": {"name": "阿澜"}}),
        section_goal=SectionGoal(
            section_id="s1",
            objective="阿澜公开旧信并承担关系代价",
            viewpoint_character_id="a",
            desired_length=500,
        ),
        story_threads=[],
    )

    assert [item.id for item in contract.required_events] == ["section_goal_objective"]
    assert contract.required_events[0].keywords
    assert contract.length_constraint.min_chars == 200
    assert contract.length_constraint.max_chars == 750


def test_contract_input_rejects_unstructured_unknown_fields() -> None:
    try:
        NarrativeContractInput.model_validate({"writer_may_infer": True})
    except ValueError as exc:
        assert "writer_may_infer" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unknown contract input was accepted")
