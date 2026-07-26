from __future__ import annotations

from story.repair_patch import (
    RepairPatch,
    RepairPatchAnchor,
    RepairPatchSet,
    RepairPatchValidator,
)
from tests.test_repair_plan import _plan_and_report


def _apply(original: str, patches: list[RepairPatch]):
    contract, event_plan, _, plan = _plan_and_report(original)
    return RepairPatchValidator().validate_and_apply(
        original_text=original,
        patch_set=RepairPatchSet(patches=patches),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )


def test_two_anchor_replace_changes_only_bracketed_text() -> None:
    original = (
        "沈砚替林秋包扎了手。"
        "海风压住窗框。沈砚准备把旧信交给林秋。灯影晃动。"
    )
    patch = RepairPatch(
        patch_type="replace",
        anchor=RepairPatchAnchor(
            before_text="海风压住窗框。",
            after_text="灯影晃动。",
        ),
        patch_text="沈砚把旧信交给林秋，林秋接过旧信并收好。",
        target_events=["handover"],
        target_end_states=["holder"],
    )

    result = _apply(original, [patch])

    assert result.report.accepted is True
    assert result.narrative_text == (
        "沈砚替林秋包扎了手。"
        "海风压住窗框。沈砚把旧信交给林秋，林秋接过旧信并收好。灯影晃动。"
    )


def test_empty_patch_list_is_repair_no_change() -> None:
    original = "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。"

    result = _apply(original, [])

    assert result.report.accepted is False
    assert [item.code for item in result.report.violations] == [
        "REPAIR_NO_CHANGE"
    ]
    assert result.narrative_text == original


def test_insert_with_identical_text_is_repair_no_change() -> None:
    original = "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。"
    patch = RepairPatch(
        patch_type="replace",
        anchor=RepairPatchAnchor(before_text="沈砚准备把旧信交给林秋。"),
        patch_text="沈砚准备把旧信交给林秋。",
        target_events=["handover"],
    )

    result = _apply(original, [patch])

    assert result.report.accepted is False
    assert "REPAIR_NO_CHANGE" in {
        item.code for item in result.report.violations
    }
