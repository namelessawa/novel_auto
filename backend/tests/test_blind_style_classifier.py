from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

classifier = importlib.import_module("classify_styles_blind")


def test_anonymous_prompt_hides_registry_keys_and_labels() -> None:
    from novel_presets import get_style_preset, list_style_keys

    keys = list_style_keys()
    _, user, mapping = classifier._build_judge_prompts(
        text="他推开门，雨落在空碗里。", style_keys=keys, salt="sample-a"
    )

    assert set(mapping.values()) == set(keys)
    assert all(candidate_id in user for candidate_id in mapping)
    for key in keys:
        preset = get_style_preset(key)
        assert key not in user
        assert preset.label not in user


def test_candidate_order_is_deterministic_but_salt_dependent() -> None:
    from novel_presets import list_style_keys

    keys = list_style_keys()
    _, first = classifier._anonymous_candidates(keys, "one")
    _, repeated = classifier._anonymous_candidates(keys, "one")
    _, second = classifier._anonymous_candidates(keys, "two")

    assert first == repeated
    assert list(first.values()) != list(second.values())


def test_normalise_maps_opaque_ids_and_rejects_duplicates() -> None:
    out = classifier._normalise_judgment(
        {
            "top3": [
                {"candidate_id": "C02", "confidence": 1.4, "evidence": "短句"},
                {"candidate_id": "C02", "confidence": 0.8},
                {"candidate_id": "C01", "confidence": "0.5"},
                {"candidate_id": "C03", "confidence": -1},
            ],
            "observed_features": "动作密集",
        },
        {"C01": "literary", "C02": "noir_cold", "C03": "warm_healing"},
    )

    assert out["valid"] is True
    assert [item["style"] for item in out["top3"]] == [
        "noir_cold", "literary", "warm_healing"
    ]
    assert [item["confidence"] for item in out["top3"]] == [1.0, 0.5, 0.0]
    assert out["observed_features"] == ["动作密集"]


def test_summary_reports_top1_top3_and_confusion() -> None:
    results = [
        {
            "scenario": "pressure",
            "expected_style": "literary",
            "judgment": {"valid": True, "top3": [
                {"style": "noir_cold"}, {"style": "literary"},
                {"style": "warm_healing"},
            ]},
        },
        {
            "scenario": "compatible",
            "expected_style": "noir_cold",
            "judgment": {"valid": True, "top3": [
                {"style": "noir_cold"}, {"style": "literary"},
                {"style": "warm_healing"},
            ]},
        },
        {
            "scenario": "compatible",
            "expected_style": "warm_healing",
            "judgment": {"valid": False, "top3": []},
        },
    ]
    summary = classifier._summarise(
        results, ["literary", "noir_cold", "warm_healing"]
    )

    assert summary["valid_samples"] == 2
    assert summary["top1_accuracy"] == 0.5
    assert summary["top3_accuracy"] == 1.0
    assert summary["confusion_matrix"]["literary"]["noir_cold"] == 1
    assert summary["top_confusions"] == [
        {"expected": "literary", "predicted": "noir_cold", "count": 1}
    ]
