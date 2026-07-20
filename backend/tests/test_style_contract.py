from __future__ import annotations

import pytest

from novel_presets import STYLE_PRESETS, StylePreset
from quality_metrics.style_contract import style_contract_report


def _report(key: str, text: str, *, strict: bool = True):
    preset = STYLE_PRESETS[key]
    return style_contract_report(key, text, preset.det_rules, strict=strict)


def test_style_snapshot_roundtrip_and_hash_are_stable() -> None:
    preset = STYLE_PRESETS["classical_chapter"]
    snapshot = preset.to_snapshot()
    restored = StylePreset.from_snapshot(snapshot)
    assert restored == preset
    assert snapshot["prompt_hash"] == preset.prompt_hash
    assert restored.prompt_hash == preset.prompt_hash


def test_first_person_missing_i_is_high_confidence() -> None:
    report = _report("first_person_immersive", "他推开门，看见灯还亮着。")
    assert report.requires_rewrite
    assert {f.code for f in report.findings} == {"first_person"}


def test_screenplay_camera_instruction_is_high_confidence() -> None:
    report = _report("screenplay_visual", "镜头推向门边。林岚抬手敲了三下。")
    assert report.requires_rewrite
    assert any(f.code == "no_camera_meta" for f in report.findings)


def test_screenplay_shot_size_label_is_high_confidence() -> None:
    report = _report("screenplay_visual", "全景，维修区尽头一盏警示灯旋转。")
    assert report.requires_rewrite
    assert any(f.code == "no_camera_meta" for f in report.findings)


def test_classical_checks_only_apply_on_strict_cadence() -> None:
    loose = _report("classical_chapter", "林岚推门而入，众人都回过头。", strict=False)
    strict = _report("classical_chapter", "林岚推门而入，众人都回过头。", strict=True)
    assert not loose.requires_rewrite
    assert strict.requires_rewrite


def test_medium_heuristic_does_not_trigger_rewrite() -> None:
    report = _report("xianxia_fast", "风停了。门外只剩下一片冷光。")
    assert any(f.severity == "medium" for f in report.findings)
    assert not report.requires_rewrite


def test_strict_style_cadence_is_deterministic_and_importance_aware() -> None:
    from agents.narrator_agent import NarratorAgent
    from memory_system.models import Event

    preset = STYLE_PRESETS["hot_blooded"]
    low = Event(
        id="low", tick=2, type="exogenous", description="过渡",
        narrative_value=3,
    )
    high = Event(
        id="high", tick=2, type="dramatic", description="关键转折",
        narrative_value=9,
    )
    assert NarratorAgent._is_strict_style_tick(preset, 1, [low]) is True
    assert NarratorAgent._is_strict_style_tick(preset, 2, [low]) is False
    assert NarratorAgent._is_strict_style_tick(preset, 3, [low]) is True
    assert NarratorAgent._is_strict_style_tick(preset, 2, [high]) is True


def test_warm_foreground_death_is_high_confidence() -> None:
    report = _report("warm_healing", "她绕过尸体，把水递给孩子。")
    assert report.requires_rewrite


def test_black_humor_contract_example_copy_is_rejected() -> None:
    report = _report(
        "black_humor",
        "职员填完七页表格。表格不会饿，填表格的人会。",
    )
    assert report.requires_rewrite
    assert any(f.code == "black_humor_originality" for f in report.findings)

    injury_copy = _report(
        "black_humor",
        "她抽完两百毫升血。规程不会失血，执行规程的机器也不会。",
    )
    assert injury_copy.requires_rewrite


@pytest.mark.asyncio
async def test_high_finding_gets_exactly_one_targeted_rewrite(mock_llm) -> None:
    from agents.narrator_agent import NarratorAgent, NarratorOutput

    preset = STYLE_PRESETS["first_person_immersive"]
    agent = NarratorAgent(enable_critic=False)
    mock_llm.set_responses([{"narrative_text": "我推开门，看见灯还亮着。"}])
    out = await agent._enforce_style_contract(
        NarratorOutput(should_narrate=True, narrative_text="他推开门，看见灯还亮着。"),
        preset=preset,
        strict=True,
        tick=1,
    )
    assert out.narrative_text.startswith("我")
    assert out.style_contract_trace["rewrite_attempted"] is True
    assert out.style_contract_trace["rewrite_adopted"] is True
    assert len(mock_llm.calls) == 1


@pytest.mark.asyncio
async def test_style_anchor_prompt_uses_same_frozen_preset(mock_llm) -> None:
    from bootstrap_prompts import generate_style_anchors

    preset = STYLE_PRESETS["hot_blooded"]
    mock_llm.set_responses([{
        "style_anchors": [{
            "excerpt": "他撞开舱门，喊出承诺，再次冲进火里。",
            "selection_reason": "动作与宣言同拍",
            "weight": 1.0,
            "scene_type": "action",
        }]
    }])
    anchors = await generate_style_anchors(
        title="机甲试验",
        positioning="热血动作",
        references="无",
        style_preset_key=preset.key,
        style_preset_snapshot=preset.to_snapshot(),
    )
    assert len(anchors) == 1
    _, user_prompt = mock_llm.calls[0]
    assert f"preset={preset.key}" in user_prompt
    assert preset.version in user_prompt
    assert preset.prompt_hash[:12] in user_prompt
    assert preset.final_checklist in user_prompt
