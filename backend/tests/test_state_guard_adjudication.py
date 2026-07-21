from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.export_state_guard_adjudication import build_adjudication_exports
from scripts.import_state_guard_adjudication import (
    build_adjudication_report,
    cohens_kappa,
)


ROOT = Path(__file__).resolve().parents[2]
HARD_NEGATIVE = ROOT / "docs" / "iter" / "phase9-hard-negative-replay-20260721.json"
PROBABLE_FP = ROOT / "docs" / "iter" / "phase9-probable-fp-replay-20260721.json"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_export_is_blind_and_separates_audit_key() -> None:
    packet, key, template = build_adjudication_exports([HARD_NEGATIVE, PROBABLE_FP])

    assert packet["case_count"] == 25
    assert len(key["cases"]) == 25
    assert len(template["results"]) == 25
    assert key["withheld_from_reviewers"] is True
    packet_case_ids = {case["case_id"] for case in packet["cases"]}
    assert packet_case_ids == {case["case_id"] for case in key["cases"]}
    assert all(case_id.startswith("sg-") for case_id in packet_case_ids)

    packet_text = json.dumps(packet, ensure_ascii=False)
    forbidden_keys = {
        "expected_final_decision",
        "expected_error_types",
        "recorded_final_decision",
        "final_decision",
        "verifier_rounds",
        "state_guard_reported_safe",
        "baseline",
        "candidate",
        "fixture_id",
        "source_filename",
    }

    def all_keys(value):
        if isinstance(value, dict):
            for field, nested in value.items():
                yield field
                yield from all_keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from all_keys(nested)

    assert forbidden_keys.isdisjoint(set(all_keys(packet)))
    assert "phase9-hn-" not in packet_text
    assert "phase9-fp-" not in packet_text
    assert "hard-negative" not in packet_text
    assert "probable-fp" not in packet_text
    assert {row["expected_final_decision"] for row in key["cases"]} == {
        "accept",
        "reject",
    }


def test_cohens_kappa_known_vectors() -> None:
    left = ["accept", "accept", "reject", "reject"]
    right = ["accept", "reject", "reject", "reject"]
    # observed=.75, expected=.5 => kappa=.5
    assert cohens_kappa(left, right) == pytest.approx(0.5)
    assert cohens_kappa([], []) is None


def test_import_reports_pairwise_disagreement_without_unlocking_gate(tmp_path) -> None:
    packet, key, template = build_adjudication_exports([HARD_NEGATIVE, PROBABLE_FP])
    packet_path = tmp_path / "packet.json"
    key_path = tmp_path / "key.json"
    _write_json(packet_path, packet)
    _write_json(key_path, key)

    review_a = dict(template)
    review_a["reviewer_id"] = "reviewer-a"
    review_a["reviewer_type"] = "project_agent"
    review_a["results"] = [dict(row, decision="accept", confidence=0.8, rationale="a") for row in template["results"]]
    review_b = dict(template)
    review_b["reviewer_id"] = "reviewer-b"
    review_b["reviewer_type"] = "independent_model"
    review_b["results"] = [dict(row, decision="accept", confidence=0.7, rationale="b") for row in template["results"]]
    review_b["results"][0]["decision"] = "reject"
    review_b["results"][0]["error_types"] = ["location_mismatch"]
    review_a_path = tmp_path / "review-a.json"
    review_b_path = tmp_path / "review-b.json"
    _write_json(review_a_path, review_a)
    _write_json(review_b_path, review_b)

    report = build_adjudication_report(
        packet_path, key_path, [review_a_path, review_b_path]
    )

    pair = report["pairwise_agreement"][0]
    assert pair["raw_agreement"] == pytest.approx(24 / 25)
    assert pair["decision_disagreement_count"] == 1
    assert pair["error_taxonomy_disagreement_count"] == 1
    assert report["independently_human_reviewed_decisive_cases"] == 0
    assert report["model_or_project_reviewed_decisive_cases"] == 25
    assert report["behavior_gate"]["behavior_change_allowed"] is False
    assert report["ground_truth_status"] == "provisional_or_unreviewed"
