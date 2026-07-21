from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.export_state_guard_adjudication import build_adjudication_exports
from scripts.import_state_guard_adjudication import (
    build_adjudication_report,
    build_disagreement_packet,
    cohens_kappa,
)
from scripts.run_blind_state_guard_review import build_parser as build_review_parser


ROOT = Path(__file__).resolve().parents[2]
HARD_NEGATIVE = ROOT / "docs" / "iter" / "phase9-hard-negative-replay-20260721.json"
PROBABLE_FP = ROOT / "docs" / "iter" / "phase9-probable-fp-replay-20260721.json"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _review(
    template: dict,
    reviewer_id: str,
    *,
    model_family: str,
    model_name: str,
    decisions: dict[str, str] | None = None,
    packet_id: str | None = None,
    packet_hash: str | None = None,
    case_ids: list[str] | None = None,
) -> dict:
    decisions = decisions or {}
    source_results = template["results"]
    if case_ids is not None:
        source_results = [row for row in source_results if row["case_id"] in case_ids]
    results = []
    for row in source_results:
        decision = decisions.get(row["case_id"], "accept")
        results.append(
            {
                "case_id": row["case_id"],
                "decision": decision,
                "error_types": (
                    ["location_mismatch"] if decision == "reject" else []
                ),
                "confidence": 0.85,
                "rationale": f"独立审查 {row['case_id']} 的事实依据。",
            }
        )
    review = deepcopy(template)
    review.update(
        {
            "packet_id": packet_id or template["packet_id"],
            "packet_sha256": packet_hash or template["packet_sha256"],
            "packet_hash": packet_hash or template["packet_sha256"],
            "reviewer_id": reviewer_id,
            "reviewer_type": "independent_model",
            "model_family": model_family,
            "model_name": model_name,
            "provider_name": model_family,
            "review_started_at": "2026-07-21T01:00:00Z",
            "review_finished_at": "2026-07-21T01:01:00Z",
            "prompt_hash": "a" * 64,
            "temperature": 0.0,
            "blind_key_accessed": False,
            "review_input_files": ["packet.json"],
            "usage": {
                "provider_calls": 1,
                "input_tokens": 100,
                "output_tokens": 20,
                "total_tokens": 120,
            },
            "raw_response_sha256": "b" * 64,
            "results": results,
        }
    )
    return review


def _exports() -> tuple[dict, dict, dict]:
    return build_adjudication_exports([HARD_NEGATIVE, PROBABLE_FP])


def test_export_is_blind_and_separates_audit_key() -> None:
    packet, key, template = _exports()

    assert packet["case_count"] == 25
    assert len(key["cases"]) == 25
    assert len(template["results"]) == 25
    assert key["withheld_from_reviewers"] is True
    packet_case_ids = {case["case_id"] for case in packet["cases"]}
    assert packet_case_ids == {case["case_id"] for case in key["cases"]}
    assert all(case_id.startswith("sg-") for case_id in packet_case_ids)
    assert len(packet["cases"][0]["questions"]) == 6
    assert all("repair_attempts" in case for case in packet["cases"])

    packet_text = json.dumps(packet, ensure_ascii=False).casefold()
    forbidden_strings = {
        "hard_negative",
        "probable_fp",
        "expected_accept",
        "expected_reject",
        "baseline_decision",
        "candidate_decision",
        "final_decision",
        "verifier_safe",
        "phase9-hn-",
        "phase9-fp-",
    }
    assert all(value not in packet_text for value in forbidden_strings)
    assert {row["expected_final_decision"] for row in key["cases"]} == {
        "accept",
        "reject",
    }
    assert template["reviewer_type"] == "independent_model"
    assert template["blind_key_accessed"] is False


def test_review_runner_has_no_blind_key_argument() -> None:
    parser = build_review_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }
    help_text = parser.format_help()
    assert "--blind-key" not in option_strings
    assert "--key" not in option_strings
    assert "--provider-file" in help_text
    assert "--out-review" in help_text


def test_cohens_kappa_known_vectors() -> None:
    left = ["accept", "accept", "reject", "reject"]
    right = ["accept", "reject", "reject", "reject"]
    assert cohens_kappa(left, right) == pytest.approx(0.5)
    assert cohens_kappa([], []) is None


def test_duplicate_reviewer_identity_is_rejected(tmp_path) -> None:
    packet, key, template = _exports()
    packet_path = tmp_path / "packet.json"
    key_path = tmp_path / "key.json"
    _write_json(packet_path, packet)
    _write_json(key_path, key)
    review_a = _review(template, "same-reviewer", model_family="glm", model_name="glm-a")
    review_b = _review(template, "same-reviewer", model_family="mimo", model_name="mimo-b")
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    _write_json(path_a, review_a)
    _write_json(path_b, review_b)

    with pytest.raises(ValueError, match="reviewer IDs must be unique"):
        build_adjudication_report(packet_path, key_path, [path_a, path_b])


def test_packet_hash_mismatch_is_rejected(tmp_path) -> None:
    packet, key, template = _exports()
    packet_path = tmp_path / "packet.json"
    key_path = tmp_path / "key.json"
    packet["cases"][0]["prose"] += "tampered"
    _write_json(packet_path, packet)
    _write_json(key_path, key)
    review = _review(template, "reviewer-a", model_family="glm", model_name="glm-a")
    review_path = tmp_path / "review.json"
    _write_json(review_path, review)

    with pytest.raises(ValueError, match="packet hash mismatch"):
        build_adjudication_report(packet_path, key_path, [review_path])


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_missing_or_duplicate_review_case_is_rejected(tmp_path, mutation) -> None:
    packet, key, template = _exports()
    packet_path = tmp_path / "packet.json"
    key_path = tmp_path / "key.json"
    _write_json(packet_path, packet)
    _write_json(key_path, key)
    review = _review(template, "reviewer-a", model_family="glm", model_name="glm-a")
    if mutation == "missing":
        review["results"].pop()
    else:
        review["results"].append(deepcopy(review["results"][0]))
    review_path = tmp_path / "review.json"
    _write_json(review_path, review)

    expected = "coverage mismatch" if mutation == "missing" else "duplicate cases"
    with pytest.raises(ValueError, match=expected):
        build_adjudication_report(packet_path, key_path, [review_path])


def test_disagreement_packet_contains_no_prior_answers() -> None:
    packet, _, _ = _exports()
    selected_ids = [packet["cases"][0]["case_id"], packet["cases"][3]["case_id"]]
    disagreement = build_disagreement_packet(packet, selected_ids)
    text = json.dumps(disagreement, ensure_ascii=False)

    assert [case["case_id"] for case in disagreement["cases"]] == selected_ids
    assert "reviewer_labels" not in text
    assert "reviewer-a" not in text
    assert "reviewer-b" not in text
    assert '"decision"' not in text


def test_third_reviewer_resolves_disagreement_without_overwriting_reviews(tmp_path) -> None:
    packet, key, template = _exports()
    first_case = packet["cases"][0]["case_id"]
    review_a = _review(template, "reviewer-a", model_family="glm", model_name="glm-a")
    review_b = _review(
        template,
        "reviewer-b",
        model_family="mimo",
        model_name="mimo-b",
        decisions={first_case: "reject"},
    )
    packet_path = tmp_path / "packet.json"
    key_path = tmp_path / "key.json"
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    for path, payload in (
        (packet_path, packet),
        (key_path, key),
        (path_a, review_a),
        (path_b, review_b),
    ):
        _write_json(path, payload)

    first_report = build_adjudication_report(packet_path, key_path, [path_a, path_b])
    disagreement = first_report["_disagreement_packet_payload"]
    adjudicator = _review(
        template,
        "reviewer-c",
        model_family="deepseek",
        model_name="deepseek-c",
        decisions={first_case: "reject"},
        packet_id=disagreement["packet_id"],
        packet_hash=disagreement["packet_sha256"],
        case_ids=[first_case],
    )
    adjudicator_path = tmp_path / "c.json"
    _write_json(adjudicator_path, adjudicator)
    final_report = build_adjudication_report(
        packet_path,
        key_path,
        [path_a, path_b],
        adjudicator_path=adjudicator_path,
    )
    gold = final_report["_gold_payload"]
    gold_case = next(case for case in gold["cases"] if case["case_id"] == first_case)

    assert gold_case["adjudication_required"] is True
    assert gold_case["adjudicator_label"] == "reject"
    assert gold_case["final_label"] == "reject"
    assert len(gold_case["reviewer_labels"]) == 3
    assert json.loads(path_a.read_text(encoding="utf-8")) == review_a
    assert json.loads(path_b.read_text(encoding="utf-8")) == review_b


def test_review_gate_blocks_when_independent_count_is_insufficient(tmp_path) -> None:
    packet, key, template = _exports()
    packet_path = tmp_path / "packet.json"
    key_path = tmp_path / "key.json"
    review_path = tmp_path / "review.json"
    _write_json(packet_path, packet)
    _write_json(key_path, key)
    _write_json(
        review_path,
        _review(template, "reviewer-a", model_family="glm", model_name="glm-a"),
    )

    report = build_adjudication_report(packet_path, key_path, [review_path])

    assert report["review_gate"]["passed"] is False
    assert report["review_gate"]["decision"] == "BLOCK_REAL_REPLAY"
    assert report["review_gate"]["behavior_change_allowed"] is False
