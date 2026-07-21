from __future__ import annotations

import json
from pathlib import Path

from scripts.convert_phase7_guard_replays import (
    convert_sources,
    replay_recorded_decision,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    ROOT / "docs" / "iter" / "phase7-gateb-sidecar-run1-glm-20260721.json",
    ROOT / "docs" / "iter" / "phase7-gateb-sidecar-run2-glm-20260721.json",
]
EXPECTED_SOURCE_HASHES = {
    "phase7-gateb-sidecar-run1-glm-20260721.json": (
        "cdc088f57d9e984caea279ea2e6d4a4ca0eaffc6fbe24d2ccaa7f8bed777317a"
    ),
    "phase7-gateb-sidecar-run2-glm-20260721.json": (
        "58a6a8ecee0e102e5b596956b651b7d355ccc37e2ffcf5927742d1483c50b9a7"
    ),
}


def test_phase7_conversion_preserves_56_unique_loss_aware_cases() -> None:
    converted = convert_sources(SOURCES)
    cases = converted["cases"]

    assert converted["summary"] == {
        "source_count": 2,
        "case_count": 56,
        "decision_counts": {"accept": 20, "reject": 36},
        "reproduced_decision_count": 56,
        "accepted_text_available_count": 20,
        "rejected_draft_available_count": 0,
        "full_repair_text_available_count": 0,
        "unreviewed_count": 56,
    }
    assert len({case["case_id"] for case in cases}) == 56
    assert all(case["decision_replay_matches_persistence"] for case in cases)
    assert all(case["review_status"] == "unreviewed" for case in cases)
    assert all(case["human_labels"] == [] for case in cases)
    assert all(case["adjudicated_label"] is None for case in cases)
    assert all(case["error_types"] == [] for case in cases)
    rejected = [
        case for case in cases if case["recorded_final_decision"] == "reject"
    ]
    assert len(rejected) == 36
    assert all(
        case["completeness"]["rejected_draft_available"] is False
        for case in rejected
    )
    assert all(
        case["completeness"]["full_repair_text_available"] is False
        for case in cases
    )


def test_phase7_conversion_hashes_sources_and_is_byte_stable() -> None:
    first = convert_sources(SOURCES)
    second = convert_sources(list(reversed(SOURCES)))

    assert {
        source["filename"]: source["sha256"]
        for source in first["source_artifacts"]
    } == EXPECTED_SOURCE_HASHES
    assert first == second
    assert json.dumps(
        first, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) == json.dumps(
        second, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    serialized = json.dumps(first, ensure_ascii=False)
    assert "coding.txt" not in serialized
    assert "credential_present" not in serialized
    assert "base_url" not in serialized


def test_recorded_decision_replay_is_trace_only() -> None:
    assert replay_recorded_decision(
        {"repair_attempted": False, "before": {"safe": True}}
    ) == "accept"
    assert replay_recorded_decision(
        {
            "repair_attempted": True,
            "before": {"safe": False},
            "adopted": True,
        }
    ) == "accept"
    assert replay_recorded_decision(
        {
            "repair_attempted": True,
            "before": {"safe": False},
            "after": {"safe": True},
        }
    ) == "reject"
