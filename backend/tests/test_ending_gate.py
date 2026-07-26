from __future__ import annotations

from story.ending_validator import EndingCompletionValidator
from story.narrative_contract import (
    EventCompletionResult,
    EndStateResult,
    NarrativeContract,
    NarrativeValidationReport,
    RequiredEndState,
)


def _contract() -> NarrativeContract:
    return NarrativeContract(
        section_id="ending",
        story_bible_revision=1,
        canonical_state_revision=1,
        contract_hash="ending-contract",
        required_end_state=[
            RequiredEndState(
                id="holder",
                path="/items/letter/holder",
                expected="lin",
            )
        ],
    )


def _report(evidence: str) -> NarrativeValidationReport:
    return NarrativeValidationReport(
        accepted=True,
        end_state_results=[
            EndStateResult(
                id="holder",
                path="/items/letter/holder",
                expected="lin",
                reached=True,
                evidence=evidence,
            )
        ],
    )


def _validate(tail: str):
    evidence = "林秋把旧信收好，旧信最终由林秋持有。"
    text = evidence + tail
    return EndingCompletionValidator().validate(
        narrative_text=text,
        contract=_contract(),
        narrative_report=_report(evidence),
        phase="initial",
    )


def test_post_resolution_expansion_detected() -> None:
    report = _validate("就在这时，一声爆炸突然响起，门外又出现危机。")

    assert report.accepted is False
    assert report.needs_compact is True
    assert report.violation_code == "POST_RESOLUTION_EXPANSION"
    assert EndingCompletionValidator.violation(report).code == (
        "POST_RESOLUTION_EXPANSION"
    )


def test_new_event_after_ending_rejected() -> None:
    report = _validate("突然有人撞开门冲入室内，新的袭击开始了。")

    assert any(item.kind == "new_event" for item in report.issues)
    assert report.accepted is False


def test_new_character_after_ending_rejected() -> None:
    report = _validate("一名陌生水手走进灯塔，所有人重新看向门口。")

    assert any(item.kind == "new_character" for item in report.issues)
    assert report.accepted is False


def test_existing_quiet_closing_is_allowed() -> None:
    report = _validate("海风掠过窗沿，灯光安静下来。")

    assert report.accepted is True
    assert report.issues == []


def test_required_event_after_early_end_state_sets_later_stop_boundary() -> None:
    end_evidence = "林秋把旧信收好，旧信最终由林秋持有。"
    event_evidence = "沈砚随后完成了契约要求的核对动作。"
    text = end_evidence + "突然响起的动静属于核对步骤。" + event_evidence
    report = _report(end_evidence).model_copy(
        update={
            "event_results": [
                EventCompletionResult(
                    event_id="verify",
                    status="completed",
                    evidence=event_evidence,
                )
            ]
        }
    )

    result = EndingCompletionValidator().validate(
        narrative_text=text,
        contract=_contract(),
        narrative_report=report,
        phase="initial",
    )

    assert result.resolution_offset == len(text)
    assert result.accepted is True
