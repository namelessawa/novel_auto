from __future__ import annotations

from story.event_execution import EventExecutionPlanBuilder
from story.models import WriterCandidate
from story.narrative_contract import (
    AllowedEntities,
    EntityReference,
    LengthConstraint,
    NarrativeContract,
    RequiredEndState,
    RequiredEvent,
)
from story.section_budget import (
    SectionBudgetPlan,
    SectionSegmentBudget,
    StyleBalanceContract,
)
from story.writer_preflight import WriterPreflightValidator


def _authorities():
    contract = NarrativeContract(
        section_id="preflight",
        story_bible_revision=1,
        canonical_state_revision=1,
        contract_hash="preflight-contract",
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
                evidence_patterns=[r"沈砚.{0,20}旧信.{0,20}林秋.{0,20}接过"],
            ),
        ],
        required_end_state=[
            RequiredEndState(
                id="quiet",
                path="/world/lighthouse_status",
                expected="quiet",
                evidence_patterns=[r"灯塔恢复平静"],
            )
        ],
        length_constraint=LengthConstraint(min_chars=1, max_chars=300),
    )
    event_plan = EventExecutionPlanBuilder().build(
        contract=contract,
        section_goal=type("Goal", (), {"section_id": "preflight"})(),
        story_threads=[],
        canonical_state=None,
    )
    budget = SectionBudgetPlan(
        section_id="preflight",
        target_chars=100,
        min_chars=70,
        max_chars=130,
        segments=[
            SectionSegmentBudget(name="opening", budget=18, max_chars=30),
            SectionSegmentBudget(name="development", budget=30, max_chars=40),
            SectionSegmentBudget(name="conflict", budget=30, max_chars=40),
            SectionSegmentBudget(name="resolution", budget=22, max_chars=30),
        ],
        stop_conditions=[
            "required_events_completed",
            "end_state_reached",
            "minimum_length_reached",
        ],
        style_balance_contract=StyleBalanceContract(
            key="literary",
            instruction="details serve events",
        ),
    )
    return contract, event_plan, budget


def _candidate(text: str) -> WriterCandidate:
    return WriterCandidate(
        narrative_text=text,
        title="交接",
        section_summary="沈砚完成包扎与交接，灯塔恢复平静。",
    )


def _valid_text() -> str:
    return (
        "海风掠过灯塔，沈砚看见林秋手上的伤口，先确认四周没有变化。"
        "沈砚取出已有的纱布，仔细替林秋包扎了手，林秋安静地点头。"
        "沈砚随后把旧信交给林秋，林秋接过旧信，确认交接动作已经完成。"
        "林秋将旧信收好，两人停下动作，灯塔恢复平静，屋内只剩海风声。"
    )


def _validate(text: str):
    contract, event_plan, budget = _authorities()
    return WriterPreflightValidator().validate(
        candidate=_candidate(text),
        contract=contract,
        event_plan=event_plan,
        budget_plan=budget,
    )


def test_short_draft_triggers_retry() -> None:
    report = _validate("沈砚替林秋包扎了手。")

    assert report.accepted is False
    assert report.retry_required is True
    assert "PREFLIGHT_TOO_SHORT" in {item.code for item in report.issues}


def test_missing_event_triggers_retry() -> None:
    text = _valid_text().replace(
        "沈砚随后把旧信交给林秋，林秋接过旧信，确认交接动作已经完成。",
        "沈砚随后看了一眼旧信，林秋没有催促，两人继续等待。",
    )
    report = _validate(text)

    assert report.event_pass is False
    assert "PREFLIGHT_EVENT_COVERAGE_LOW" in {
        item.code for item in report.issues
    }


def test_missing_end_state_triggers_retry() -> None:
    report = _validate(_valid_text().replace("灯塔恢复平静", "灯塔仍未安静"))

    assert report.end_state_pass is False
    assert "PREFLIGHT_END_STATE_UNREACHABLE" in {
        item.code for item in report.issues
    }


def test_valid_draft_skips_retry() -> None:
    report = _validate(_valid_text())

    assert report.accepted is True
    assert report.retry_required is False
    assert report.length_pass is True
    assert report.structure_pass is True
    assert [item.name for item in report.segments] == [
        "opening",
        "development",
        "conflict",
        "resolution",
    ]
