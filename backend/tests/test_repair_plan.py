from __future__ import annotations

from story.event_execution import EventExecutionPlanBuilder
from story.models import ValidationReport
from story.narrative_contract import (
    AllowedEntities,
    EntityReference,
    LengthConstraint,
    NarrativeContract,
    RequiredEndState,
    RequiredEvent,
)
from story.narrative_validator import NarrativeContractValidator
from story.repair_plan import (
    RepairPlanBuilder,
    RepairRegressionValidator,
)


def _contract() -> NarrativeContract:
    return NarrativeContract(
        section_id="repair",
        story_bible_revision=1,
        canonical_state_revision=1,
        contract_hash="repair-contract",
        allowed_entities=AllowedEntities(
            characters=[
                EntityReference(id="shen", name="沈砚"),
                EntityReference(id="lin", name="林秋"),
            ],
            items=[EntityReference(id="letter", name="旧信")],
        ),
        required_events=[
            RequiredEvent(
                id="bandage",
                actor="shen",
                action="包扎林秋的手",
                target="lin",
                evidence_patterns=[r"沈砚.{0,20}包扎.{0,20}林秋"],
            ),
            RequiredEvent(
                id="handover",
                actor="shen",
                action="把旧信交给林秋",
                target="lin",
                evidence_patterns=[r"沈砚.{0,20}旧信.{0,20}林秋.{0,20}(?:接过|收下)"],
            ),
        ],
        required_end_state=[
            RequiredEndState(
                id="holder",
                path="/items/letter/holder",
                expected="lin",
            )
        ],
        length_constraint=LengthConstraint(min_chars=20, max_chars=300),
    )


def _plan_and_report(text: str):
    contract = _contract()
    event_plan = EventExecutionPlanBuilder().build(
        contract=contract,
        section_goal=type("Goal", (), {"section_id": "repair"})(),
        story_threads=[],
        canonical_state=None,
    )
    report = NarrativeContractValidator().validate(
        contract, text, event_execution_plan=event_plan
    )
    plan = RepairPlanBuilder().build(
        transaction_id="tx",
        contract=contract,
        event_plan=event_plan,
        narrative_report=report,
        state_report=ValidationReport(accepted=True),
        narrative_text=text,
    )
    return contract, event_plan, report, plan


def test_repair_plan_preserves_completed_event_and_targets_only_missing_event() -> None:
    _, _, _, plan = _plan_and_report(
        "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。"
    )

    assert [item.event_id for item in plan.incomplete_events] == ["handover"]
    assert [item.event_id for item in plan.must_preserve_spans] == ["bandage"]
    assert plan.wrong_end_states[0].state_id == "holder"
    assert "实际" in plan.incomplete_events[0].minimum_completion_evidence
    assert any("StateDelta" in item for item in plan.forbidden_changes)


def test_repair_regression_is_rejected() -> None:
    contract, event_plan, _, plan = _plan_and_report(
        "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。"
    )
    repaired = "沈砚把旧信交给林秋，林秋接过旧信并收好。"
    final = NarrativeContractValidator().validate(
        contract, repaired, event_execution_plan=event_plan
    )

    violations = RepairRegressionValidator().validate(
        plan=plan,
        final_report=final,
        repaired_text=repaired,
    )

    assert [item.code for item in violations] == ["REPAIR_REGRESSION"]


def test_repair_preserving_completed_event_has_no_regression() -> None:
    contract, event_plan, _, plan = _plan_and_report(
        "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。"
    )
    repaired = (
        "沈砚替林秋包扎了手。"
        "沈砚把旧信交给林秋，林秋接过旧信并收好。"
    )
    final = NarrativeContractValidator().validate(
        contract, repaired, event_execution_plan=event_plan
    )

    assert RepairRegressionValidator().validate(
        plan=plan,
        final_report=final,
        repaired_text=repaired,
    ) == []
