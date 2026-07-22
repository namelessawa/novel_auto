from __future__ import annotations

from copy import deepcopy

from scripts.run_author_longrange import _request_id
from scripts.run_author_stage1_matrix import aggregate


def _matrix() -> dict:
    combinations = []
    for combo in range(15):
        sections = []
        for section in range(3):
            sections.append(
                {
                    "section_id": f"ch0001_s{section + 1:04d}",
                    "transaction_id": f"combo_{combo}_section_{section}",
                    "committed": True,
                    "narrative_contract_pass": True,
                    "state_conflict_count": 0,
                    "repair_performed": section == 2,
                    "repair_success": section == 2,
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "repair_tokens": 25 if section == 2 else 0,
                    "total_tokens": 150,
                    "latency_seconds": 2.0,
                }
            )
        combinations.append(
            {
                "run_id": f"run_{combo}",
                "theme": "theme",
                "style": "style",
                "integrity": [],
                "summary": {
                    "attempted": 3,
                    "committed": 3,
                    "hard_rejects": 0,
                    "provider_errors": 0,
                },
                "sections": sections,
            }
        )
    return {"combinations": combinations}


def test_stage1_aggregate_requires_and_accepts_complete_45_section_matrix() -> None:
    summary = aggregate(_matrix(), expected_combinations=15, sections_per_combo=3)

    assert summary["gate"] == "STAGE1_PASS"
    assert summary["attempted"] == summary["committed"] == 45
    assert summary["contract_pass_rate"] == 1.0
    assert summary["repair_rate"] == 0.3333
    assert summary["repair_success_rate"] == 1.0
    assert summary["total_tokens"] == 6750
    assert all(summary["gate_checks"].values())


def test_stage1_aggregate_fails_completed_matrix_with_one_reject() -> None:
    matrix = deepcopy(_matrix())
    failed = matrix["combinations"][0]
    failed["sections"][0]["committed"] = False
    failed["sections"][0]["narrative_contract_pass"] = False
    failed["summary"]["committed"] = 2
    failed["summary"]["hard_rejects"] = 1

    summary = aggregate(matrix, expected_combinations=15, sections_per_combo=3)

    assert summary["gate"] == "STAGE1_FAIL"
    assert summary["committed"] == 44
    assert summary["hard_rejects"] == 1
    assert summary["gate_checks"]["all_45_sections_committed"] is False


def test_real_resume_uses_new_request_id_after_provider_failure() -> None:
    failures = [
        {"section": 2, "attempt": 1},
        {"section": 1, "attempt": 1},
        {"section": 2, "attempt": 2},
    ]

    request_id, prior_failures = _request_id(2, failures)

    assert request_id == "section_0002_retry_02"
    assert prior_failures == 2
