from __future__ import annotations

import json
from pathlib import Path

from scripts.build_state_guard_calibration import (
    ERROR_TYPES,
    build_dataset,
    repair_review_text,
)


ROOT = Path(__file__).resolve().parents[2]
RECORDED = ROOT / "docs" / "iter" / "phase8-phase7-guard-recorded-v1.json"
MANUAL = (
    Path(__file__).parent
    / "fixtures"
    / "state_guard_calibration"
    / "manual_cases_v1.json"
)
GENERATED = (
    ROOT
    / "docs"
    / "iter"
    / "state_guard_calibration"
    / "phase8-state-guard-calibration-v1.json"
)


def test_calibration_dataset_has_73_loss_aware_double_reviewed_cases() -> None:
    dataset = build_dataset(RECORDED, MANUAL)

    assert dataset["summary"]["case_count"] == 73
    assert dataset["summary"]["phase7_case_count"] == 56
    assert dataset["summary"]["synthetic_case_count"] == 17
    assert dataset["summary"]["decision_counts"] == {
        "accept": 27,
        "reject": 7,
        "ambiguous": 39,
    }
    assert dataset["summary"]["decisive_case_count"] == 34
    assert dataset["summary"]["double_reviewed_count"] == 73
    assert dataset["summary"]["review_agreement_count"] == 73
    assert dataset["summary"]["human_reviewed_count"] == 0
    assert len({case["case_id"] for case in dataset["cases"]}) == 73
    assert all(len(case["reviews"]) == 2 for case in dataset["cases"])
    assert all(
        review["human_reviewer"] is False
        for case in dataset["cases"]
        for review in case["reviews"]
    )
    assert all(
        case["adjudication"]["human_reviewed"] is False
        for case in dataset["cases"]
    )


def test_phase7_missing_rejected_drafts_remain_ambiguous() -> None:
    dataset = build_dataset(RECORDED, MANUAL)
    phase7 = [
        case
        for case in dataset["cases"]
        if case["source_type"] == "phase7_recorded_trace"
    ]
    recorded_rejects = [
        case for case in phase7 if case["recorded_final_decision"] == "reject"
    ]
    recorded_accepts = [
        case for case in phase7 if case["recorded_final_decision"] == "accept"
    ]

    assert len(recorded_rejects) == 36
    assert len(recorded_accepts) == 20
    assert all(
        case["adjudication"]["expected_final_decision"] == "ambiguous"
        for case in recorded_rejects
    )
    assert all(
        case["completeness"]["rejected_draft_available"] is False
        for case in recorded_rejects
    )
    assert all(
        "narrative_text" not in case["review_material"]
        for case in recorded_rejects
    )
    assert all(
        case["adjudication"]["expected_final_decision"] == "accept"
        for case in recorded_accepts
    )


def test_calibration_covers_every_required_error_type() -> None:
    dataset = build_dataset(RECORDED, MANUAL)

    assert dataset["taxonomy"] == ERROR_TYPES
    assert all(
        dataset["summary"]["error_type_counts"][error] > 0
        for error in ERROR_TYPES
    )


def test_review_mojibake_decode_is_additive_and_readable() -> None:
    assert repair_review_text("¾¯±¨") == "警报"
    assert repair_review_text("已经是正常中文") == "已经是正常中文"
    dataset = build_dataset(RECORDED, MANUAL)
    first_phase7 = next(
        case
        for case in dataset["cases"]
        if case["source_type"] == "phase7_recorded_trace"
    )
    material = json.dumps(first_phase7["review_material"], ensure_ascii=False)
    assert "警报" in material
    assert "本段结束前" in material


def test_calibration_artifact_is_reproducible_and_source_hashed() -> None:
    first = build_dataset(RECORDED, MANUAL)
    second = build_dataset(RECORDED, MANUAL)
    persisted = json.loads(GENERATED.read_text(encoding="utf-8"))

    assert first == second == persisted
    assert first["dataset_sha256"] == (
        "573b2d822b8ecc3d4caf2609781d1fa2c26cd3ced46e8b25eba4f8dcc5b43441"
    )
    assert first["source_artifacts"] == [
        {
            "filename": "phase8-phase7-guard-recorded-v1.json",
            "sha256": (
                "c495d3c8a791d6ac698594c4e9b97ff8bff5e6c86059d66bea856be7b5d07be2"
            ),
            "cases_sha256": (
                "529f42977b2cb7f39f480a48d42d84bc5a987a966c8263b139a0e4a6171cf8c2"
            ),
        },
        {
            "filename": "manual_cases_v1.json",
            "sha256": (
                "bc94e2cb9269ae58df1b654075f92867543a7a37e8bea2752ea65518307839e9"
            ),
        },
    ]
    serialized = json.dumps(first, ensure_ascii=False)
    assert "coding.txt" not in serialized
    assert "credential_present" not in serialized
    assert "base_url" not in serialized
