from __future__ import annotations

from story.models import ValidationReport
from story.narrative_validator import NarrativeContractValidator
from story.repair_patch import RepairPatchSet, RepairPatchValidator
from story.repair_plan import RepairPlanBuilder, repair_patch_prompt_payload
from tests.test_repair_plan import _contract
from story.event_execution import EventExecutionPlanBuilder


def _compact_case():
    contract = _contract()
    event_plan = EventExecutionPlanBuilder().build(
        contract=contract,
        section_goal=type("Goal", (), {"section_id": "repair"})(),
        story_threads=[],
        canonical_state=None,
    )
    required = (
        "沈砚替林秋包扎了手。"
        "沈砚把旧信交给林秋，林秋接过旧信并收好。"
    )
    details = [
        "海风反复擦过窗沿，桌面的灯影缓慢摇晃，屋内没有人离开。",
        "潮声又一次贴近石墙，灯芯仍旧轻轻发颤，沉默没有改变动作结果。",
        "窗纸被潮气压得发暗，灯影沿着桌角来回移动，房间依旧安静。",
        "远处浪声绕回塔身，微光在旧木纹上停留，二人没有再说话。",
        "门缝里的风缓缓退去，桌面残留着同样的暖色，四周仍无变化。",
        "潮湿气息贴着墙面游走，灯芯轻响了一下，沉默继续铺在室内。",
        "玻璃上的雾痕没有散开，微光仍压在纸面，屋内维持原样。",
        "海浪在石阶下重复回落，暗影慢慢缩短，空气依旧潮湿。",
        "风从窗框边缘再次穿过，灯焰随之偏斜，桌旁仍然寂静。",
        "塔外潮声一遍遍靠近，木桌上的光没有离开，房间保持沉默。",
    ]
    text = required + "".join(details) + "林秋继续保管旧信。"
    report = NarrativeContractValidator().validate(
        contract,
        text,
        event_execution_plan=event_plan,
    )
    plan = RepairPlanBuilder().build(
        transaction_id="compact",
        contract=contract,
        event_plan=event_plan,
        narrative_report=report,
        state_report=ValidationReport(accepted=True),
        narrative_text=text,
    )
    payload = repair_patch_prompt_payload(plan, text)
    compact_payloads = [
        item for item in payload["required_patches"]
        if item["patch_type"] == "compact"
    ]
    return contract, event_plan, text, report, plan, compact_payloads


def test_compact_removes_duplicate_style_detail() -> None:
    contract, event_plan, text, _, plan, compact_payloads = _compact_case()
    result = RepairPatchValidator().validate_and_apply(
        original_text=text,
        patch_set=RepairPatchSet.model_validate({"patches": compact_payloads}),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )

    assert compact_payloads
    assert result.report.accepted is True
    assert result.report.char_delta < 0
    assert len(result.narrative_text) < len(text)


def test_compact_preserves_event() -> None:
    contract, event_plan, text, _, plan, compact_payloads = _compact_case()
    result = RepairPatchValidator().validate_and_apply(
        original_text=text,
        patch_set=RepairPatchSet.model_validate({"patches": compact_payloads}),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )
    final = NarrativeContractValidator().validate(
        contract,
        result.narrative_text,
        event_execution_plan=event_plan,
    )

    assert all(item.status == "completed" for item in final.event_results)


def test_compact_preserves_end_state() -> None:
    contract, event_plan, text, _, plan, compact_payloads = _compact_case()
    result = RepairPatchValidator().validate_and_apply(
        original_text=text,
        patch_set=RepairPatchSet.model_validate({"patches": compact_payloads}),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )
    final = NarrativeContractValidator().validate(
        contract,
        result.narrative_text,
        event_execution_plan=event_plan,
    )

    assert all(item.reached for item in final.end_state_results)


def test_compact_cannot_remove_evidence() -> None:
    contract, event_plan, text, _, plan, compact_payloads = _compact_case()
    patch = compact_payloads[0] | {
        "anchor": {"start": "沈砚替林秋包扎了手。", "end": ""}
    }
    result = RepairPatchValidator().validate_and_apply(
        original_text=text,
        patch_set=RepairPatchSet.model_validate({"patches": [patch]}),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )

    assert {
        item.code for item in result.report.violations
    } & {"COMPACT_NOT_AUTHORIZED", "REPAIR_REGRESSION"}


def test_compact_cannot_add_facts() -> None:
    contract, event_plan, text, _, plan, compact_payloads = _compact_case()
    patch = compact_payloads[0] | {"patch_text": "一名陌生人走进灯塔。"}
    result = RepairPatchValidator().validate_and_apply(
        original_text=text,
        patch_set=RepairPatchSet.model_validate({"patches": [patch]}),
        plan=plan,
        contract=contract,
        event_plan=event_plan,
    )

    assert "PATCH_COMPACT_HAS_TEXT" in {
        item.code for item in result.report.violations
    }
