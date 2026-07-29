from __future__ import annotations

import pytest
from pydantic import ValidationError

from story.repair_patch import RepairPatch, RepairPatchAnchor, RepairPatchSet
from story.repair_plan import repair_patch_prompt_payload
from story.writer import AuthorWriter
from tests.test_repair_plan import _plan_and_report


def test_repair_patch_models_local_insert() -> None:
    patch_set = RepairPatchSet(
        patches=[
            RepairPatch(
                patch_type="insert",
                anchor=RepairPatchAnchor(before_text="林秋打开门。"),
                patch_text="沈砚把旧信交给调查员，调查员接过并收好。",
                target_events=["handover"],
                target_end_states=["holder"],
            )
        ]
    )

    assert patch_set.patches[0].max_chars == 300
    assert patch_set.patches[0].anchor.before_text == "林秋打开门。"


def test_repair_patch_requires_an_exact_anchor() -> None:
    with pytest.raises(ValidationError):
        RepairPatch(
            patch_type="insert",
            anchor=RepairPatchAnchor(),
            patch_text="局部补丁。",
        )


def test_repair_patch_schema_forbids_whole_narrative_field() -> None:
    with pytest.raises(ValidationError):
        RepairPatchSet.model_validate(
            {
                "patches": [],
                "narrative_text": "不允许返回完整正文",
            }
        )


def test_repair_patch_cannot_return_state_change_without_evidence() -> None:
    with pytest.raises(ValidationError):
        RepairPatch.model_validate(
            {
                "patch_type": "insert",
                "anchor": {"before_text": "林秋打开门。"},
                "patch_text": "沈砚把旧信交给林秋。",
                "target_events": ["handover"],
                "state_delta": [
                    {
                        "op": "set",
                        "path": "/world/weather",
                        "value": "暴雨",
                        "evidence": "",
                    }
                ],
            }
        )


def test_repair_prompt_exposes_only_provider_text_requests() -> None:
    original = "沈砚替林秋包扎了手。沈砚准备把旧信交给林秋。"
    _, _, _, plan = _plan_and_report(original)
    payload = repair_patch_prompt_payload(plan, original)

    assert payload["execution_mode"] == "SERVER_OWNED_TEMPLATE_TEXT_ONLY"
    assert payload["provider_patch_requests"] == []
    assert payload["server_owned_actions"]
    assert "patch_id 和 patch_text" in AuthorWriter.REPAIR_SYSTEM_PROMPT
    assert "Do not return patch_type, anchor" in payload["final_instruction"]
