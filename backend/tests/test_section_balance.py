from __future__ import annotations

from story.ending_validator import EndingCompletionReport
from story.event_execution import EventExecutionPlan
from story.models import SectionGoal
from story.narrative_contract import (
    EventCompletionResult,
    EndStateResult,
    LengthConstraint,
    NarrativeContract,
    NarrativeValidationReport,
)
from story.section_budget import SectionBudgetPlanBuilder
from story.section_length_validator import (
    SectionBalanceValidator,
    SectionLengthValidator,
)
from story.writing_plan import SectionWritingPlanBuilder


def _budget(style: str = "literary"):
    contract = NarrativeContract(
        section_id="balance",
        story_bible_revision=1,
        canonical_state_revision=1,
        contract_hash="balance-contract",
        length_constraint=LengthConstraint(min_chars=900, max_chars=1100),
    )
    event_plan = EventExecutionPlan(
        section_id="balance",
        contract_hash=contract.contract_hash,
        length_constraint=contract.length_constraint,
        style_constraints={"key": style},
    )
    writing_plan = SectionWritingPlanBuilder().build(
        contract=contract,
        event_plan=event_plan,
        section_goal=SectionGoal(
            objective="完成既有事件",
            desired_length=900,
            narrative_constraints={
                "length_constraint": {"min_chars": 900, "max_chars": 1100}
            },
        ),
        style_contract={"key": style},
    )
    return SectionBudgetPlanBuilder().build(
        writing_plan=writing_plan,
        style_contract={"key": style},
    )


def test_segment_budget_respected() -> None:
    plan = _budget()

    assert plan.target_chars == 1030
    assert [item.budget for item in plan.segments] == [185, 309, 309, 227]
    assert [item.max_chars for item in plan.segments] == [235, 359, 359, 277]
    assert sum(item.budget for item in plan.segments) == plan.target_chars
    assert plan.stop_conditions == [
        "required_events_completed",
        "end_state_reached",
        "minimum_length_reached",
    ]


def test_section_max_exceeded() -> None:
    report = SectionLengthValidator().validate(
        "字" * 1101,
        _budget(),
        phase="final",
    )

    assert report.accepted is False
    assert report.violation_code == "NARRATIVE_TOO_LONG"


def test_section_min_failed() -> None:
    report = SectionLengthValidator().validate(
        "字" * 899,
        _budget(),
        phase="final",
    )

    assert report.accepted is False
    assert report.violation_code == "NARRATIVE_TOO_SHORT"


def test_balance_requires_event_end_state_and_length_together() -> None:
    length_report = SectionLengthValidator().validate(
        "字" * 1000,
        _budget(),
        phase="final",
    )
    narrative_report = NarrativeValidationReport(
        accepted=False,
        event_results=[
            EventCompletionResult(event_id="event", status="missing")
        ],
        end_state_results=[
            EndStateResult(
                id="end",
                path="/items/letter/holder",
                expected="lin",
                reached=True,
            )
        ],
    )
    report = SectionBalanceValidator.validate(
        narrative_report=narrative_report,
        length_report=length_report,
        ending_report=EndingCompletionReport(phase="final"),
        phase="final",
    )

    assert report.length_pass is True
    assert report.end_state_pass is True
    assert report.event_pass is False
    assert report.accepted is False


def test_warm_balance_limits_emotional_description() -> None:
    contract = _budget("warm_healing").style_balance_contract

    assert any("two consecutive" in item for item in contract.limits)
    assert any("repeated emotional" in item for item in contract.forbidden)
