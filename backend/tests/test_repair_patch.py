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


def test_length_expand_prompt_has_zero_numeral_authority() -> None:
    original = "沈砚替林秋包扎了手。沈砚把旧信交给林秋。海风掠过灯塔。"
    _, _, _, plan = _plan_and_report(original)
    plan = plan.model_copy(
        update={
            "length_adjustment": plan.length_adjustment.model_copy(
                update={
                    "action": "add",
                    "target_chars": 80,
                    "desired_final_chars": 220,
                    "max_add_chars": 120,
                    "min_chars": 200,
                    "max_chars": 260,
                }
            ),
            "patch_templates": [],
        }
    )
    payload = repair_patch_prompt_payload(plan, original)

    assert payload["provider_patch_requests"]
    request = payload["provider_patch_requests"][0]
    lexical = request["patch_text_lexical_contract"]
    assert lexical["scope"] == "patch_text_only"
    assert lexical["allowed_number_tokens"] == []
    assert lexical["forbidden_pattern"] == (
        "[0-9零〇一二两三四五六七八九十百千万]"
    )
    assert lexical["self_check_before_return"] is True
    assert lexical["schema_version_and_patch_id_exempt"] is True
    assert "逐个自检 patch_text" in AuthorWriter.REPAIR_SYSTEM_PROMPT
    assert "schema_version and patch_id are exempt" in payload["final_instruction"]
