from __future__ import annotations

import pytest

from story.event_execution import EventExecutionPlanBuilder
from story.models import EventEvidenceHint
from story.narrative_contract import (
    AllowedEntities,
    EntityReference,
    LengthConstraint,
    NarrativeContract,
    RequiredEndState,
    RequiredEvent,
)
from story.narrative_validator import NarrativeContractValidator


def _contract() -> NarrativeContract:
    return NarrativeContract(
        section_id="events",
        story_bible_revision=1,
        canonical_state_revision=1,
        contract_hash="event-contract",
        allowed_entities=AllowedEntities(
            characters=[
                EntityReference(id="shen", name="沈砚"),
                EntityReference(id="lin", name="林秋"),
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
                evidence_patterns=[r"沈砚.{0,30}(?:交给|递给|递到).{0,20}调查员.{0,30}(?:接过|收下)"],
            )
        ],
        required_end_state=[
            RequiredEndState(
                id="holder",
                path="/items/letter/holder",
                expected="investigator",
            )
        ],
        length_constraint=LengthConstraint(min_chars=1, max_chars=1000),
    )


def _status(text: str, hints=None) -> str:
    contract = _contract()
    plan = EventExecutionPlanBuilder().build(
        contract=contract,
        section_goal=type("Goal", (), {"section_id": "events"})(),
        story_threads=[],
        canonical_state=None,
    )
    report = NarrativeContractValidator().validate(
        contract,
        text,
        event_execution_plan=plan,
        event_evidence=hints,
    )
    return report.event_results[0].status


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("雨声盖住了脚步。", "missing"),
        ("沈砚提到把旧信交给调查员这件事。", "mentioned"),
        ("沈砚准备把旧信交给调查员。", "started"),
        ("沈砚试图把旧信交给调查员，却被门挡住。", "attempted"),
        ("沈砚并未把旧信交给调查员。", "contradicted"),
        ("林秋把旧信交给调查员，调查员接过旧信。", "wrong_actor"),
        ("沈砚把旧信交给林秋，林秋接过旧信。", "wrong_target"),
        ("沈砚把旧信递给调查员，调查员接过旧信并收好。", "completed"),
    ],
)
def test_event_completion_states(text: str, expected: str) -> None:
    assert _status(text) == expected


def test_writer_evidence_hint_cannot_self_certify_future_intention() -> None:
    text = "沈砚即将把旧信交给调查员。"
    hints = [EventEvidenceHint(event_id="handover", evidence=text)]

    assert _status(text, hints) == "started"


def test_item_not_transferred_and_final_holder_not_reached() -> None:
    report = NarrativeContractValidator().validate(
        _contract(),
        "沈砚走向调查员，仍把旧信留在自己口袋里。",
    )

    assert report.accepted is False
    assert report.event_results[0].status != "completed"
    assert report.end_state_results[0].reached is False


def test_item_transfer_completed_and_holder_reached() -> None:
    report = NarrativeContractValidator().validate(
        _contract(),
        "沈砚把旧信递给调查员，调查员接过旧信并收进内袋。",
    )

    assert report.accepted is True
    assert report.event_results[0].status == "completed"
    assert report.end_state_results[0].reached is True


def test_later_transfer_overrides_earlier_holder_evidence() -> None:
    report = NarrativeContractValidator().validate(
        _contract(),
        (
            "沈砚把旧信递给调查员，调查员接过旧信并收好。"
            "随后沈砚把信接回去，放回自己胸口的内袋。"
        ),
    )

    assert report.accepted is False
    assert report.end_state_results[0].reached is False
    assert report.end_state_results[0].violation_code == "END_STATE_WRONG_HOLDER"


def test_leading_pronoun_remains_holder_when_other_character_is_observed() -> None:
    report = NarrativeContractValidator().validate(
        _contract(),
        (
            "沈砚把旧信交给调查员。调查员低头核完信上的记录。"
            "他看了沈砚一眼，把信纸塞回封套，封套折进内袋，扣好纽扣。"
        ),
    )

    assert report.end_state_results[0].reached is True


def test_natural_multisentence_transfer_can_complete_without_exact_template() -> None:
    report = NarrativeContractValidator().validate(
        _contract(),
        (
            "沈砚把油纸封搁在桌面上，示意调查员查看。"
            "调查员从封套里抽出旧信，读完后把信收进自己的内袋。"
        ),
    )

    assert report.event_results[0].status == "completed"
    assert report.end_state_results[0].reached is True


def test_walking_to_door_does_not_count_as_opening_it() -> None:
    contract = NarrativeContract(
        section_id="door",
        story_bible_revision=1,
        canonical_state_revision=1,
        contract_hash="door-contract",
        allowed_entities=AllowedEntities(
            characters=[EntityReference(id="shen", name="沈砚")],
            items=[EntityReference(id="door", name="铁门")],
        ),
        required_events=[
            RequiredEvent(
                id="open-door",
                actor="shen",
                action="打开铁门",
                target="door",
            )
        ],
        required_end_state=[
            RequiredEndState(id="door-open", path="/world/door/open", expected=True)
        ],
        length_constraint=LengthConstraint(min_chars=1, max_chars=1000),
    )
    report = NarrativeContractValidator().validate(
        contract,
        "沈砚走向铁门，伸手准备打开它，但铁门仍然紧闭。",
    )

    assert report.event_results[0].status in {"started", "attempted", "contradicted"}
    assert report.end_state_results[0].reached is False


def test_composite_verification_and_continued_custody_are_both_required() -> None:
    contract = NarrativeContract(
        section_id="verify",
        story_bible_revision=1,
        canonical_state_revision=1,
        contract_hash="verify-contract",
        allowed_entities=AllowedEntities(
            characters=[
                EntityReference(id="lin", name="林秋"),
                EntityReference(id="shen", name="沈砚"),
            ],
            items=[
                EntityReference(
                    id="letter",
                    name="旧信",
                    aliases=["信纸", "信封", "封套"],
                )
            ],
        ),
        required_events=[
            RequiredEvent(
                id="verify-third",
                actor="lin",
                action="核对旧信第3处记录并继续保管",
                target="letter",
            )
        ],
        required_end_state=[
            RequiredEndState(
                id="holder",
                path="/items/letter/holder",
                expected="lin",
            )
        ],
        length_constraint=LengthConstraint(min_chars=1, max_chars=1000),
    )
    completed = NarrativeContractValidator().validate(
        contract,
        "林秋展开旧信，沿第三行逐字比照，确认记录无误。她把信收进自己的内袋继续保管。",
    )
    reversed_state = NarrativeContractValidator().validate(
        contract,
        (
            "林秋展开旧信，沿第三行逐字比照，确认记录无误。"
            "随后沈砚把信接回去，放回自己胸口的内袋。"
        ),
    )

    assert completed.accepted is True
    assert completed.event_results[0].status == "completed"
    assert reversed_state.accepted is False
    assert reversed_state.event_results[0].status == "contradicted"
    assert reversed_state.end_state_results[0].violation_code == "END_STATE_WRONG_HOLDER"


@pytest.mark.parametrize(
    "prose",
    [
        "林秋展开旧信，指尖沿第三行逐字移动，末了说对得上。她把信收进内袋。",
        "林秋展开旧信，对第三处记录一字一字对过去，确认无误后把信塞回内袋。",
        "林秋展开旧信，逐字比对第三处，见内容一一吻合，复藏于内襟暗袋。",
    ],
)
def test_composite_verification_accepts_natural_completed_wording(prose: str) -> None:
    contract = NarrativeContract(
        section_id="verify-natural",
        story_bible_revision=1,
        canonical_state_revision=1,
        contract_hash="verify-natural-contract",
        allowed_entities=AllowedEntities(
            characters=[EntityReference(id="lin", name="林秋")],
            items=[EntityReference(id="letter", name="旧信", aliases=["信纸", "信封"])],
        ),
        required_events=[
            RequiredEvent(
                id="verify-third",
                actor="lin",
                action="核对旧信第3处记录并继续保管",
                target="letter",
            )
        ],
        required_end_state=[
            RequiredEndState(id="holder", path="/items/letter/holder", expected="lin")
        ],
        length_constraint=LengthConstraint(min_chars=1, max_chars=1000),
    )

    report = NarrativeContractValidator().validate(contract, prose)

    assert report.accepted is True
    assert report.event_results[0].status == "completed"
