from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from scripts.build_phase9_guard_fixtures import build_hard_negative_suite
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
