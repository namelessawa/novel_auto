from __future__ import annotations

from scripts.run_p6_length_anchor_recovery import (
    _bad_commit_count,
    _violation_count,
    assess_g1,
    assess_g2,
)


def _section(*, length: int = 1000) -> dict:
    return {
        "narrative_length": length,
        "required_events_completed": 1,
        "required_events_total": 1,
        "end_states_reached": 1,
        "end_states_total": 1,
        "repair_audit_codes": [],
        "repair_patch_codes": [],
        "narrative_violation_codes": [],
        "state_violation_codes": [],
    }


def _matrix(*, count: int, first_pass: int, repairs: int = 0) -> dict:
    sections = [_section() for _ in range(count)]
    return {
        "combinations": [{"sections": sections}],
        "summary": {
            "attempted": count,
            "committed": count,
            "contract_pass": count,
            "writer_first_pass_pass": first_pass,
            "repairs": repairs,
            "repair_success": repairs,
            "provider_calls": count + repairs,
            "planner_calls": 0,
            "writer_retries": 0,
            "provider_errors": 0,
            "data_integrity_violations": [],
            "hard_fact_error_commits": 0,
            "state_conflict_commits": 0,
            "illegal_thread_change_commits": 0,
            "evidenceless_state_delta_commits": 0,
        },
    }


def test_g1_accepts_exact_green_historical_case() -> None:
    assert assess_g1(_matrix(count=1, first_pass=1))["status"] == "passed"


def test_g1_rejects_underlength_commit() -> None:
    matrix = _matrix(count=1, first_pass=1)
    matrix["combinations"][0]["sections"][0]["narrative_length"] = 899
    result = assess_g1(matrix)
    assert result["status"] == "failed"
    assert result["checks"]["length_900_1100"] is False


def test_g1_rejects_anchor_failure_even_when_committed() -> None:
    matrix = _matrix(count=1, first_pass=0, repairs=1)
    matrix["combinations"][0]["sections"][0]["repair_patch_codes"] = [
        "PATCH_ANCHOR_NOT_FOUND"
    ]
    result = assess_g1(matrix)
    assert result["status"] == "failed"
    assert result["metrics"]["anchor_failures"] == 1


def test_g1_rejects_post_resolution_expansion() -> None:
    matrix = _matrix(count=1, first_pass=0, repairs=1)
    matrix["combinations"][0]["sections"][0]["narrative_violation_codes"] = [
        "POST_RESOLUTION_EXPANSION"
    ]
    assert assess_g1(matrix)["status"] == "failed"


def test_g1_rejects_planner_or_full_retry_calls() -> None:
    matrix = _matrix(count=1, first_pass=1)
    matrix["summary"]["planner_calls"] = 1
    matrix["summary"]["writer_retries"] = 1
    result = assess_g1(matrix)
    assert result["checks"]["planner_calls_zero"] is False
    assert result["checks"]["full_retry_calls_zero"] is False


def test_g2_accepts_strict_15_section_gate() -> None:
    assert assess_g2(_matrix(count=15, first_pass=9, repairs=6))["status"] == "passed"


def test_g2_requires_all_15_commits_and_contracts() -> None:
    matrix = _matrix(count=15, first_pass=9)
    matrix["summary"]["committed"] = 14
    matrix["summary"]["contract_pass"] = 14
    result = assess_g2(matrix)
    assert result["checks"]["committed_15"] is False
    assert result["checks"]["contract_15"] is False


def test_g2_requires_at_least_14_lengths_in_hard_range() -> None:
    matrix = _matrix(count=15, first_pass=9)
    sections = matrix["combinations"][0]["sections"]
    sections[0]["narrative_length"] = 899
    sections[1]["narrative_length"] = 1101
    result = assess_g2(matrix)
    assert result["status"] == "failed"
    assert result["metrics"]["length_in_range"] == 13


def test_g2_requires_nine_first_passes_and_at_most_six_repairs() -> None:
    matrix = _matrix(count=15, first_pass=8, repairs=7)
    result = assess_g2(matrix)
    assert result["checks"]["writer_first_pass_at_least_9"] is False
    assert result["checks"]["repair_dependency_at_most_6"] is False


def test_g2_requires_ninety_percent_repair_success() -> None:
    matrix = _matrix(count=15, first_pass=9, repairs=6)
    matrix["summary"]["repair_success"] = 5
    result = assess_g2(matrix)
    assert result["status"] == "failed"
    assert result["metrics"]["repair_success_rate"] < 0.9


def test_g2_rejects_more_than_two_provider_calls_per_section() -> None:
    matrix = _matrix(count=15, first_pass=9)
    matrix["summary"]["provider_calls"] = 31
    assert assess_g2(matrix)["status"] == "failed"


def test_bad_commit_count_includes_transaction_integrity() -> None:
    summary = {
        "hard_fact_error_commits": 1,
        "state_conflict_commits": 2,
        "illegal_thread_change_commits": 3,
        "evidenceless_state_delta_commits": 4,
        "data_integrity_violations": ["revision_jump", "duplicate_transaction"],
    }
    assert _bad_commit_count(summary) == 12


def test_violation_count_reads_all_repair_and_validator_code_fields() -> None:
    section = _section()
    section["repair_audit_codes"] = ["PATCH_ANCHOR_NOT_FOUND"]
    section["repair_patch_codes"] = ["PATCH_ANCHOR_NOT_FOUND"]
    section["narrative_violation_codes"] = ["PATCH_ANCHOR_NOT_FOUND"]
    section["state_violation_codes"] = ["PATCH_ANCHOR_NOT_FOUND"]
    assert _violation_count([section], "PATCH_ANCHOR_NOT_FOUND") == 4
