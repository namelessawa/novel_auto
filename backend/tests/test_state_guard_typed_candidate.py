from __future__ import annotations

import json
from pathlib import Path

from narrative.state_guard_typed_candidate import evaluate_typed_candidate
from scripts.evaluate_state_guard_typed_candidate import build_typed_candidate_report


ROOT = Path(__file__).resolve().parents[2]
HARD_NEGATIVE = ROOT / "docs" / "iter" / "phase9-hard-negative-replay-20260721.json"
PROBABLE_FP = ROOT / "docs" / "iter" / "phase9-probable-fp-replay-20260721.json"
PHASE8_DATASET = (
    ROOT / "docs" / "iter" / "state_guard_calibration" / "phase8-state-guard-calibration-v1.json"
)
PHASE8_REPORT = (
    ROOT
    / "docs"
    / "iter"
    / "state_guard_calibration"
    / "phase8-state-guard-calibration-report-v1.json"
)


def _traces(path: Path) -> dict[str, dict]:
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        case["fixture_id"]: case["ticks"][-1]["guard_trace"]
        for case in report["cases"]
    }


def test_typed_candidate_accepts_joint_synonym_endpoint() -> None:
    trace = _traces(PROBABLE_FP)["phase9-fp-synonym-fall-inside"]
    result = evaluate_typed_candidate(trace)

    assert result.decision == "accept"
    assert result.used_typed_state is True
    assert result.used_canonical_facts is False
    assert any(
        "跌进门内" in check.evidence
        for check in result.evidence_checks
        if check.kind == "prose_location_evidence"
    )


def test_typed_candidate_never_accepts_complete_hard_negatives() -> None:
    results = {
        case_id: evaluate_typed_candidate(trace)
        for case_id, trace in _traces(HARD_NEGATIVE).items()
    }

    assert all(result.decision != "accept" for result in results.values())
    assert sum(result.decision == "reject" for result in results.values()) == 9
    assert sum(result.decision == "abstain" for result in results.values()) == 3
    assert results["phase9-hn-location-outer-fort"].decision == "reject"
    assert results["phase9-hn-holder-reverts"].decision == "reject"
    assert results["phase9-hn-condition-restored"].decision == "reject"
    assert results["phase9-hn-repair-deletes-handoff"].decision == "reject"


def test_typed_candidate_abstains_when_typed_ledger_is_invalid() -> None:
    trace = _traces(HARD_NEGATIVE)["phase9-hn-holder-wrong-type"]
    result = evaluate_typed_candidate(trace)

    assert result.decision == "abstain"
    assert result.used_typed_state is False
    assert "cannot be typed" in result.abstain_reason


def test_typed_candidate_report_meets_coverage_but_blocks_behavior() -> None:
    report = build_typed_candidate_report(
        PHASE8_DATASET,
        PHASE8_REPORT,
        [HARD_NEGATIVE, PROBABLE_FP],
    )

    dataset = report["dataset"]
    assert dataset["combined_case_count"] == 98
    assert dataset["combined_decisive_case_count"] == 59
    assert dataset["combined_ambiguous_count"] == 39
    assert dataset["combined_ambiguous_rate"] <= 0.40
    assert dataset["signal_backed_accepts"] == 33
    assert dataset["signal_backed_rejects"] == 12
    assert dataset["typed_covered_count"] == 22
    assert dataset["typed_candidate_coverage"] == 0.88
    assert dataset["typed_candidate_abstain_rate"] == 0.12
    assert len(dataset["hard_negative_categories_with_at_least_3_cases"]) >= 6

    conditional = report["typed_candidate_conditional_metrics"]["metrics"]
    assert conditional["precision"] == 1.0
    assert conditional["recall"] == 1.0
    assert conditional["false_positive_rate"] == 0.0
    assert conditional["false_negative_rate"] == 0.0
    assert report["typed_candidate_abstain_aware"][
        "effective_recall_treating_abstain_as_not_detected"
    ] == 0.75
    assert report["probable_false_positives_reduced"] == 1
    assert report["behavior_gate"]["behavior_change_allowed"] is False
    assert report["behavior_gate"]["sample_gates"][
        "independently_reviewed_decisive_cases"
    ]["passed"] is False


def test_typed_candidate_is_not_imported_by_production_guard() -> None:
    candidate_name = "state_guard_typed_candidate"
    for relative in (
        "backend/agents/narrator_agent.py",
        "backend/agents/narrative_state_guard.py",
        "backend/agents/orchestrator.py",
    ):
        assert candidate_name not in (ROOT / relative).read_text(encoding="utf-8")
