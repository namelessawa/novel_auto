from __future__ import annotations

from story.event_execution import (
    EventExecutionPlanBuilder,
    event_execution_plan_prompt_payload,
)
from story.models import CanonicalState, SectionGoal, StoryBible
from story.narrative_contract import (
    AllowedEntities,
    EntityReference,
    NarrativeContractBuilder,
    NarrativeContractInput,
    RequiredEndState,
    RequiredEvent,
)


def _inputs():
    bible = StoryBible(
        premise="旧信必须在天亮前交付。",
        theme="责任",
        setting_summary="现实灯塔。",
        style_contract={"key": "noir_cold"},
    )
    state = CanonicalState(
        characters={
            "shen": {"name": "沈砚"},
            "investigator": {"name": "调查员"},
        },
        items={"letter": {"name": "旧信", "holder": "shen"}},
    )
    goal = SectionGoal(
        section_id="ch0001_s0001",
        objective="沈砚把旧信交给调查员并让对方接收",
        viewpoint_character_id="shen",
        involved_characters=["shen", "investigator"],
        narrative_constraints=NarrativeContractInput(
            allowed_entities=AllowedEntities(
                characters=[
                    EntityReference(id="shen", name="沈砚"),
                    EntityReference(id="investigator", name="调查员"),
                ],
                items=[EntityReference(id="letter", name="旧信")],
            ),
            required_events=[
                RequiredEvent(
                    id="handover",
                    actor="shen",
                    action="把旧信交给调查员",
                    target="investigator",
                ),
                RequiredEvent(
                    id="receive",
                    actor="investigator",
                    action="接过旧信",
                    target="letter",
                ),
            ],
            required_end_state=[
                RequiredEndState(
                    id="letter_holder",
                    path="/items/letter/holder",
                    expected="investigator",
                )
            ],
        ),
    )
    return bible, state, goal


def test_event_execution_plan_is_deterministic_and_ordered() -> None:
    bible, state, goal = _inputs()
    contract = NarrativeContractBuilder().build(
        story_bible=bible,
        canonical_state=state,
        section_goal=goal,
        story_threads=[],
    )
    builder = EventExecutionPlanBuilder()
    first = builder.build(
        contract=contract,
        section_goal=goal,
        story_threads=[],
        canonical_state=state,
        style_contract=bible.style_contract,
    )
    second = builder.build(
        contract=contract,
        section_goal=goal,
        story_threads=[],
        canonical_state=state,
        style_contract=bible.style_contract,
    )

    assert first == second
    assert first.contract_hash == contract.contract_hash
    assert [item.id for item in first.ordered_events] == ["handover", "receive"]
    assert [item.order for item in first.ordered_events] == [1, 2]
    assert first.ordered_events[0].completion_type == "item_transfer"
    assert first.required_end_states[0].expected == "investigator"


def test_event_execution_plan_prompt_explains_non_completion() -> None:
    bible, state, goal = _inputs()
    contract = NarrativeContractBuilder().build(
        story_bible=bible,
        canonical_state=state,
        section_goal=goal,
        story_threads=[],
    )
    plan = EventExecutionPlanBuilder().build(
        contract=contract,
        section_goal=goal,
        story_threads=[],
        canonical_state=state,
        style_contract=bible.style_contract,
    )

    payload = event_execution_plan_prompt_payload(plan)

    assert payload["ordered_events"][0]["actor"] == "shen"
    assert "准备……" in payload["non_completion_examples"]
    assert "实际完成" in payload["instruction"]
