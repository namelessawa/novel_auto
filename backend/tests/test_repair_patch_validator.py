from __future__ import annotations

import pytest

from story.repair_patch import RepairPatch, RepairPatchAnchor, RepairPatchSet
from tests.test_repair_plan import _plan_and_report


def _valid_patch(
    *,
    patch_type: str = "insert",
    before_text: str,
    patch_text: str,
) -> RepairPatch:
    return RepairPatch(
        patch_type=patch_type,
        anchor=RepairPatchAnchor(before_text=before_text),
        patch_text=patch_text,
        target_events=["handover"],
        target_end_states=["holder"],
    )


def _validate(original: str, patches: list[RepairPatch]):
    from story.repair_patch import RepairPatchValidator

    contract, event_plan, _, plan = _plan_and_report(original)
    return RepairPatchValidator().validate_and_apply(
        original_text=original,
        patch_set=RepairPatchSet(patches=patches),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )


def test_insert_success() -> None:
    original = "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。"
    patch = _valid_patch(
        before_text=original,
        patch_text="沈砚把旧信交给林秋，林秋接过旧信并收好。",
    )

    result = _validate(original, [patch])

    assert result.report.accepted is True
    assert result.narrative_text.endswith("林秋接过旧信并收好。")


def test_replace_success() -> None:
    original = "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。海风停了。"
    patch = _valid_patch(
        patch_type="replace",
        before_text="沈砚准备把旧信交给林秋。",
        patch_text="沈砚把旧信交给林秋，林秋接过旧信并收好。",
    )

    result = _validate(original, [patch])

    assert result.report.accepted is True
    assert "准备" not in result.narrative_text


def test_delete_success_for_explicit_unsupported_addition() -> None:
    from story.repair_patch import RepairPatchValidator

    original = (
        "沈砚替林秋包扎了手。父亲会替他们处理。"
        "沈砚把旧信交给林秋，林秋接过旧信并收好。"
    )
    contract, event_plan, _, plan = _plan_and_report(original)
    plan = plan.model_copy(
        update={
            "unsupported_additions": [
                {
                    "code": "UNSUPPORTED_KINSHIP_ADDED",
                    "evidence": "父亲",
                    "message": "未授权亲属",
                }
            ]
        }
    )
    patch = RepairPatch(
        patch_type="delete",
        anchor=RepairPatchAnchor(before_text="父亲"),
        patch_text="",
    )

    result = RepairPatchValidator().validate_and_apply(
        original_text=original,
        patch_set=RepairPatchSet(patches=[patch]),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )

    assert result.report.accepted is True
    assert "父亲" not in result.narrative_text


@pytest.mark.parametrize(
    ("patch", "expected_code"),
    [
        (
            _valid_patch(
                before_text="不存在的锚点",
                patch_text="沈砚把旧信交给林秋，林秋接过旧信并收好。",
            ),
            "PATCH_ANCHOR_NOT_FOUND",
        ),
        (
            _valid_patch(
                before_text="重复。",
                patch_text="沈砚把旧信交给林秋，林秋接过旧信并收好。",
            ),
            "PATCH_ANCHOR_AMBIGUOUS",
        ),
        (
            RepairPatch(
                patch_type="insert",
                anchor=RepairPatchAnchor(before_text="结尾。"),
                patch_text=(
                    "沈砚把旧信交给林秋，林秋接过旧信并收好。" + "风" * 300
                ),
                target_events=["handover"],
                target_end_states=["holder"],
            ),
            "PATCH_TOO_LONG",
        ),
    ],
)
def test_invalid_anchor_or_length(
    patch: RepairPatch,
    expected_code: str,
) -> None:
    original = "沈砚替林秋包扎了手。重复。重复。结尾。"

    result = _validate(original, [patch])

    assert expected_code in {item.code for item in result.report.violations}


@pytest.mark.parametrize(
    ("unsafe_text", "expected_code"),
    [
        (
            "沈砚把旧信交给林秋，林秋接过收好，一个陌生水手名叫周迟。",
            "PATCH_ADDS_CHARACTER",
        ),
        (
            "沈砚把旧信交给林秋，林秋接过收好，父亲在旁等候。",
            "PATCH_ADDS_KINSHIP",
        ),
        (
            "沈砚在2026年7月把旧信交给林秋，林秋接过收好。",
            "PATCH_ADDS_DATE",
        ),
        (
            "沈砚把旧信交给林秋，林秋接过收好，三百条人命已无可挽回。",
            "PATCH_ADDS_CASUALTY",
        ),
        (
            "沈砚把旧信交给林秋，林秋接过收好，多年前曾经服役。",
            "PATCH_ADDS_BACKSTORY",
        ),
        (
            "沈砚把旧信交给林秋，林秋接过收好，从此世界上永远可以复活。",
            "PATCH_ADDS_WORLD_RULE",
        ),
        (
            "沈砚把旧信交给林秋，林秋接过收好，另有新的阴谋。",
            "PATCH_ADDS_STORY_THREAD",
        ),
    ],
)
def test_patch_safety_rejects_new_facts(
    unsafe_text: str,
    expected_code: str,
) -> None:
    original = "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。"
    patch = _valid_patch(before_text=original, patch_text=unsafe_text)

    result = _validate(original, [patch])

    assert expected_code in {item.code for item in result.report.violations}


def test_patch_cannot_delete_approved_event() -> None:
    original = "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。"
    patch = RepairPatch(
        patch_type="delete",
        anchor=RepairPatchAnchor(before_text="沈砚替林秋包扎了手。"),
        patch_text="",
        target_events=["handover"],
    )

    result = _validate(original, [patch])

    assert "REPAIR_REGRESSION" in {
        item.code for item in result.report.violations
    }
