from __future__ import annotations

import pytest
from pydantic import ValidationError

from story.chapter_plan import (
    ChapterPlan,
    ChapterPlanBuilder,
    chapter_plan_prompt_payload,
)
from story.event_execution import EventExecutionPlan, PlannedEvent
from story.narrative_contract import RequiredEndState
from story.section_budget import (
    SectionBudgetPlan,
    SectionSegmentBudget,
    StyleBalanceContract,
)


def plan_authorities() -> tuple[EventExecutionPlan, SectionBudgetPlan]:
    event_plan = EventExecutionPlan(
        section_id="ch0001_s0001",
        contract_hash="frozen-contract",
        ordered_events=[
            PlannedEvent(
                id="inspect",
                order=1,
                actor="protagonist",
                action="核对旧信",
                target="letter",
            ),
            PlannedEvent(
                id="handover",
                order=2,
                actor="protagonist",
                action="交出旧信",
                target="investigator",
            ),
        ],
        required_end_states=[
            RequiredEndState(
                id="letter_holder",
                path="/items/letter/holder",
                expected="investigator",
            )
        ],
    )
    budget_plan = SectionBudgetPlan(
        section_id="ch0001_s0001",
        target_chars=1000,
        min_chars=900,
        max_chars=1100,
        segments=[
            SectionSegmentBudget(name="opening", budget=180, max_chars=230),
            SectionSegmentBudget(name="development", budget=300, max_chars=350),
            SectionSegmentBudget(name="conflict", budget=300, max_chars=350),
            SectionSegmentBudget(name="resolution", budget=220, max_chars=270),
        ],
        stop_conditions=[
            "required_events_completed",
            "end_state_reached",
            "minimum_length_reached",
        ],
        style_balance_contract=StyleBalanceContract(
            key="literary",
            instruction="Style controls expression only.",
        ),
    )
    return event_plan, budget_plan


def test_valid_plan_is_closed_and_serializable() -> None:
    event_plan, budget_plan = plan_authorities()

    plan = ChapterPlanBuilder().build(
        event_plan=event_plan,
        budget_plan=budget_plan,
    )
    payload = chapter_plan_prompt_payload(plan)

    assert ChapterPlan.model_validate(payload) == plan
    assert [item.purpose for item in plan.segments] == [
        "opening",
        "development",
        "conflict",
        "resolution",
    ]
    assert sum(item.target_chars for item in plan.segments) == 1000
    assert sorted(
        event_id for segment in plan.segments for event_id in segment.events
    ) == ["handover", "inspect"]


@pytest.mark.parametrize(
    "authority_field",
    ["state_delta", "threads_opened", "memory_records"],
)
def test_chapter_plan_schema_cannot_carry_authority_mutations(
    authority_field: str,
) -> None:
    event_plan, budget_plan = plan_authorities()
    payload = ChapterPlanBuilder().build(
        event_plan=event_plan,
        budget_plan=budget_plan,
    ).model_dump(mode="json")
    payload[authority_field] = [{"id": "illegal"}]

    with pytest.raises(ValidationError):
        ChapterPlan.model_validate(payload)
