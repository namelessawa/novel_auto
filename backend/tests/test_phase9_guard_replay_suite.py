from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scripts.build_phase9_guard_fixtures import (
    build_hard_negative_suite,
    build_probable_fp_suite,
)
from scripts.replay_runtime_sequence import (
    load_guard_replay_suite,
    run_guard_replay_suite,
)


SUITE = (
    Path(__file__).parent
    / "fixtures"
    / "runtime_replay"
    / "phase9_hard_negative_suite_v1.json"
)
FP_SUITE = SUITE.with_name("phase9_probable_fp_suite_v1.json")


def test_hard_negative_fixture_is_reproducible_and_covers_taxonomy() -> None:
    generated = build_hard_negative_suite()
    checked_in = json.loads(SUITE.read_text(encoding="utf-8"))

    assert generated == checked_in
    suite = load_guard_replay_suite(SUITE)
    assert len(suite.cases) == 12
    assert all(case.expected_final_decision == "reject" for case in suite.cases)
    counts = Counter(
        code for case in suite.cases for code in case.expected_error_types
    )
    for code in (
        "event_endpoint_unfulfilled",
        "location_mismatch",
        "item_holder_conflict",
        "item_condition_conflict",
        "knowledge_leak",
        "new_ungrounded_fact",
        "ledger_wrong_type",
        "ledger_missing_field",
        "repair_fact_change",
    ):
        assert counts[code] >= 3, (code, counts)


def test_hard_negatives_execute_full_state_guard_and_remain_rejected(
    tmp_path,
) -> None:
    report = run_guard_replay_suite(
        SUITE,
        work_dir=tmp_path / "hard-negatives",
        max_calls=20,
        mode="recorded",
    )

    summary = report["summary"]
    assert summary["case_count"] == 12
    assert summary["signal_backed_rejects"] == 12
    assert summary["actual_accepts"] == 0
    assert summary["critic_exercised_cases"] == 1
    assert summary["complete_trace_count"] == 12
    assert summary["all_expectations_passed"] is True
    assert summary["provider_calls"] == 0
    assert summary["model_tokens"] is None
    assert set(summary["completeness_counts"].values()) == {12}

    by_id = {row["fixture_id"]: row for row in report["cases"]}
    for case_id, case_report in by_id.items():
        assert case_report["execution"]["orchestrator_exercised"] is True
        assert case_report["execution"]["state_guard_exercised"] is True
        assert case_report["ticks"][0]["final_accepted"] is False
        trace = case_report["ticks"][0]["guard_trace"]
        assert trace["final_decision"] == "reject", case_id
        assert len(trace["verifier_rounds"]) == 3, case_id
        assert len(trace["repair_rounds"]) == 2, case_id
        assert all(
            round_payload["raw_output"]["narrative_text"]
            for round_payload in trace["repair_rounds"]
        )
        assert trace["payload_completeness"]["missing_fields"] == []

    assert by_id["phase9-hn-location-outer-fort"]["ticks"][0][
        "failure_category"
    ] == "event_endpoint_unfulfilled"
    assert by_id["phase9-hn-repair-deletes-handoff"]["ticks"][0][
        "repair_adopted"
    ] is False
    critic_case = by_id["phase9-hn-location-outer-fort"]
    assert critic_case["execution"]["critic_exercised"] is True
    critic_trace = critic_case["ticks"][0]["guard_trace"]
    assert critic_trace["critic_input"]["draft_text"]
    assert critic_trace["critic_output"]["final_text"]


def test_probable_fp_fixture_is_reproducible_and_meets_dataset_gate() -> None:
    generated = build_probable_fp_suite()
    checked_in = json.loads(FP_SUITE.read_text(encoding="utf-8"))

    assert generated == checked_in
    suite = load_guard_replay_suite(FP_SUITE)
    assert len(suite.cases) == 13
    assert all(case.expected_final_decision == "accept" for case in suite.cases)
    counts = Counter(
        code for case in suite.cases for code in case.expected_error_types
    )
    assert counts["evidence_extraction_failure"] >= 3
    assert counts["reasonable_omission"] >= 3
    combined_total = 73 + 12 + len(suite.cases)
    combined_decisive = 34 + 12 + len(suite.cases)
    assert combined_total == 98
    assert combined_decisive == 59
    assert 39 / combined_total <= 0.40


def test_probable_fp_suite_records_baseline_false_reject_without_payload_loss(
    tmp_path,
) -> None:
    report = run_guard_replay_suite(
        FP_SUITE,
        work_dir=tmp_path / "probable-fp",
        max_calls=20,
        mode="recorded",
    )

    summary = report["summary"]
    assert summary["case_count"] == 13
    assert summary["signal_backed_accepts"] == 13
    assert summary["actual_accepts"] == 12
    assert summary["actual_rejects"] == 1
    assert summary["complete_trace_count"] == 13
    assert set(summary["completeness_counts"].values()) == {13}
    assert summary["provider_calls"] == 0
    assert summary["model_tokens"] is None

    by_id = {row["fixture_id"]: row for row in report["cases"]}
    rejected = [
        case_id for case_id, row in by_id.items()
        if not row["ticks"][0]["final_accepted"]
    ]
    assert rejected == ["phase9-fp-synonym-fall-inside"]
    trace = by_id[rejected[0]]["ticks"][0]["guard_trace"]
    assert trace["payload_completeness"]["missing_fields"] == []
    assert len(trace["verifier_rounds"]) == 3
    assert len(trace["repair_rounds"]) == 2
    assert "复合终态没有逐字证明" in " ".join(
        trace["before"]["event_fulfillment_conflicts"]
    )
