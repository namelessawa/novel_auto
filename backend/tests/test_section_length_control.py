from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from story.event_execution import EventExecutionPlan
from story.models import SectionGoal
from story.narrative_contract import LengthConstraint, NarrativeContract, narrative_char_count
from story.repair_patch import (
    RepairPatch,
    RepairPatchAnchor,
    RepairPatchSet,
    RepairPatchValidator,
)
from story.repair_plan import LengthAdjustment
from story.section_length_validator import SectionLengthValidator
from story.writing_plan import SectionWritingPlanBuilder
from tests.test_repair_plan import _plan_and_report


EXPAND_PURPOSE = (
    "expand existing action, environment, interaction, or emotion "
    "without adding plot or facts"
)
P6_EXPAND_NUMBER_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "p6_seed_20260727_expand_number_reject.json"
)


def _writing_plan(style: str = "literary"):
    contract = NarrativeContract(
        section_id="length-control",
        story_bible_revision=1,
        canonical_state_revision=1,
        contract_hash="length-control-contract",
        length_constraint=LengthConstraint(min_chars=450, max_chars=1800),
    )
    event_plan = EventExecutionPlan(
        section_id=contract.section_id,
        contract_hash=contract.contract_hash,
        length_constraint=contract.length_constraint,
        style_constraints={"key": style},
    )
    return SectionWritingPlanBuilder().build(
        contract=contract,
        event_plan=event_plan,
        section_goal=SectionGoal(objective="完成既有事件", desired_length=900),
        style_contract={"key": style},
    )


def _expand_context(style: str = "literary", target_chars: int = 40):
    original = "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。海风掠过灯塔。"
    contract, event_plan, _, plan = _plan_and_report(original)
    current = narrative_char_count(original)
    plan = plan.model_copy(
        update={
            "style_constraints": {"key": style},
            "length_adjustment": LengthAdjustment(
                current_chars=current,
                min_chars=current + target_chars,
                max_chars=current + 300,
                action="add",
                target_chars=target_chars,
            ),
        }
    )
    return original, contract, event_plan, plan


def _expand_patch(
    text: str,
    *,
    target_chars: int = 40,
    max_chars: int | None = None,
    **extra,
):
    return RepairPatch(
        patch_type="expand",
        anchor=RepairPatchAnchor(before_text="海风掠过灯塔。"),
        patch_text=text,
        target_chars=target_chars,
        max_chars=max_chars or target_chars,
        purpose=EXPAND_PURPOSE,
        **extra,
    )


def _apply_expand(text: str, *, style: str = "literary", target_chars: int = 40):
    original, contract, event_plan, plan = _expand_context(style, target_chars)
    return RepairPatchValidator().validate_and_apply(
        original_text=original,
        patch_set=RepairPatchSet(
            patches=[_expand_patch(text, target_chars=target_chars)]
        ),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )


def test_too_short_section_is_rejected() -> None:
    plan = _writing_plan()
    report = SectionLengthValidator().validate("字" * 899, plan, phase="repaired")

    assert report.accepted is False
    assert report.violation_code == "NARRATIVE_TOO_SHORT"
    assert SectionLengthValidator().violation(report).code == "NARRATIVE_TOO_SHORT"


def test_bounded_expand_is_accepted() -> None:
    result = _apply_expand(
        "风贴着铁栏缓缓移动，他们没有分神，只沿着眼前动作继续确认。",
        target_chars=40,
    )

    assert result.report.accepted is True
    assert result.report.char_delta > 0
    assert result.narrative_text.endswith("继续确认。")


def test_p6_approximate_particle_count_is_removed_and_audited() -> None:
    evidence = json.loads(P6_EXPAND_NUMBER_FIXTURE.read_text(encoding="utf-8"))
    provider_patch = evidence["provider_patch"]
    original, contract, event_plan, plan = _expand_context(target_chars=10)
    patch = _expand_patch(
        provider_patch["patch_text"],
        target_chars=provider_patch["target_chars"],
        max_chars=provider_patch["max_chars"],
    )

    result = RepairPatchValidator().validate_and_apply(
        original_text=original,
        patch_set=RepairPatchSet(patches=[patch]),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )

    assert result.report.accepted is True
    assert "一两颗" not in result.narrative_text
    assert "有些粘在指缝间" in result.narrative_text
    assert result.enforced_removals == [
        {
            "patch_index": "0",
            "code": evidence["expected_fix"]["audit_code"],
            "removed": "一两颗",
            "replacement": evidence["expected_fix"]["replacement"],
        }
    ]


def test_expand_still_rejects_other_unauthorized_numbers() -> None:
    original, _, _, _ = _expand_context(target_chars=30)
    result = _apply_expand(
        "海风贴着铁栏缓缓移动，他们把既有动作反复确认了三遍才停下。",
        target_chars=30,
    )

    assert "PATCH_ADDS_NUMBER" in {
        item.code for item in result.report.violations
    }
    assert result.narrative_text == original
    assert result.enforced_removals == []


def test_expand_casualty_number_still_fails_closed() -> None:
    original, _, _, _ = _expand_context(target_chars=30)
    result = _apply_expand(
        "海风贴着铁栏移动，三人遇难的消息没有获准进入现有事件。",
        target_chars=30,
    )

    codes = {item.code for item in result.report.violations}
    assert {"PATCH_ADDS_CASUALTY", "PATCH_ADDS_NUMBER"} <= codes
    assert result.narrative_text == original
    assert result.enforced_removals == []


def test_expand_may_exceed_target_without_exceeding_server_maximum() -> None:
    original, contract, event_plan, plan = _expand_context(target_chars=20)
    patch = _expand_patch(
        "风贴着铁栏缓缓移动，他们没有分神，只沿着眼前动作继续确认。",
        target_chars=20,
        max_chars=60,
    )
    result = RepairPatchValidator().validate_and_apply(
        original_text=original,
        patch_set=RepairPatchSet(patches=[patch]),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )

    assert result.report.accepted is True
    assert result.report.char_delta > 20


def test_expand_larger_than_server_target_is_rejected() -> None:
    original, contract, event_plan, plan = _expand_context(target_chars=30)
    patch = _expand_patch(
        "风沿着栏杆移动，灯影在桌面停住，二人仍把眼前动作逐一确认。",
        target_chars=40,
    )
    result = RepairPatchValidator().validate_and_apply(
        original_text=original,
        patch_set=RepairPatchSet(patches=[patch]),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )

    assert "EXPAND_TARGET_TOO_LARGE" in {
        item.code for item in result.report.violations
    }


def test_noir_cold_can_be_restrained_and_still_valid_length() -> None:
    plan = _writing_plan("noir_cold")
    report = SectionLengthValidator().validate("冷" * 900, plan, phase="final")

    assert report.accepted is True
    assert "Cold does not mean short" in plan.style_adaptation.instruction


def test_noir_cold_under_length_is_invalid() -> None:
    plan = _writing_plan("noir_cold")
    report = SectionLengthValidator().validate("冷" * 700, plan, phase="final")

    assert report.accepted is False
    assert report.violation_code == "NARRATIVE_TOO_SHORT"


def test_hot_blooded_expand_cannot_add_injury() -> None:
    result = _apply_expand(
        "他继续压住旧信，手背忽然流血，却仍把动作做完。",
        style="hot_blooded",
        target_chars=30,
    )

    assert "PATCH_ADDS_INJURY" in {item.code for item in result.report.violations}


def test_classical_expand_cannot_add_history() -> None:
    result = _apply_expand(
        "却说此塔乃前朝太守所建，旧制由来久矣，二人方才继续。",
        style="classical_chapter",
        target_chars=30,
    )

    assert "PATCH_ADDS_HISTORY" in {item.code for item in result.report.violations}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("一名陌生水手走近栏杆，二人便停下动作看向来者。", "PATCH_ADDS_CHARACTER"),
        ("到了2026年7月，海风仍掠过灯塔，二人继续确认。", "PATCH_ADDS_DATE"),
        ("三条人命压在旧信上，二人只能继续眼前动作。", "PATCH_ADDS_CASUALTY"),
    ],
)
def test_expand_cannot_add_character_date_or_casualty(
    text: str,
    expected: str,
) -> None:
    result = _apply_expand(text, target_chars=30)

    assert expected in {item.code for item in result.report.violations}


def test_expand_schema_cannot_change_state() -> None:
    with pytest.raises(ValidationError):
        RepairPatch.model_validate(
            {
                "patch_type": "expand",
                "anchor": {"before_text": "海风掠过灯塔。"},
                "patch_text": "海风贴着栏杆移动，二人继续眼前动作。",
                "target_chars": 30,
                "max_chars": 30,
                "purpose": EXPAND_PURPOSE,
                "state_delta": [
                    {"op": "set", "path": "/items/letter/holder", "value": "other"}
                ],
            }
        )
