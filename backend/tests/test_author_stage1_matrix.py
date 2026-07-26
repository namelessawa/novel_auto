from __future__ import annotations

from copy import deepcopy

from scripts.analyze_author_longrange import analyze, render_markdown
from scripts.run_author_longrange import _request_id
from scripts.run_author_stage1_matrix import _combo_integrity, aggregate


def _matrix() -> dict:
    combinations = []
    for combo in range(15):
        theme = (
            "reality_mystery",
            "action_conflict",
            "warm_relationship",
        )[combo // 5]
        style = (
            "literary",
            "noir_cold",
            "warm_healing",
            "hot_blooded",
            "classical_chapter",
        )[combo % 5]
        sections = []
        for section in range(3):
            sections.append(
                {
                    "section_id": f"ch0001_s{section + 1:04d}",
                    "transaction_id": f"combo_{combo}_section_{section}",
                    "committed": True,
                    "story_bible_revision": 1,
                    "canonical_revision_before": section + 1,
                    "canonical_revision_after": section + 2,
                    "canonical_revision": section + 2,
                    "narrative_contract_pass": True,
                    "narrative_validation_history_codes": [],
                    "state_validation_history_codes": [],
                    "proposal_drop_codes": [],
                    "repair_audit_codes": [],
                    "state_conflict_count": 0,
                    "illegal_thread_change_commits": 0,
                    "evidenceless_state_delta_commits": 0,
                    "repair_performed": section == 2,
                    "repair_success": section == 2,
                    "repair_patch_count": 1 if section == 2 else 0,
                    "repair_patch_types": ["insert"] if section == 2 else [],
                    "writer_calls": 2 if section == 2 else 1,
                    "threads_open": section + 1,
                    "threads_opened_count": 1,
                    "threads_advanced_count": int(section > 0),
                    "threads_resolved_count": 0,
                    "main_conflict_progress": int(section > 0),
                    "memory_records_total": section + 1,
                    "memory_records_selected": section,
                    "memory_record_ids_added": [f"memory_{combo}_{section}"],
                    "memory_selected_ids": (
                        [f"memory_{combo}_0"] if section == 2 else []
                    ),
                    "style_contract_pass": True,
                    "style_drift_warning": False,
                    "opening_overlap": 0.1,
                    "consecutive_ngram_overlap": 0.2,
                    "narrative_length": 900,
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
                "theme": theme,
                "style": style,
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
    return {
        "stage": "stage1_real_matrix",
        "evidence_boundary": {
            "deterministic": True,
            "recorded": False,
            "real_provider": True,
            "human_review": False,
            "llm_judge": False,
        },
        "combinations": combinations,
    }


def test_stage1_aggregate_requires_and_accepts_complete_45_section_matrix() -> None:
    summary = aggregate(_matrix(), expected_combinations=15, sections_per_combo=3)

    assert summary["gate"] == "STAGE1_PASS"
    assert summary["attempted"] == summary["committed"] == 45
    assert summary["contract_pass_rate"] == 1.0
    assert summary["repair_rate"] == 0.3333
    assert summary["repair_success_rate"] == 1.0
    assert summary["provider_calls"] == 60
    assert summary["total_tokens"] == 6750
    assert all(summary["gate_checks"].values())


def test_stage1_aggregate_allows_one_reject_within_43_of_45_gate() -> None:
    matrix = deepcopy(_matrix())
    failed = matrix["combinations"][0]
    failed["sections"][0]["committed"] = False
    failed["sections"][0]["narrative_contract_pass"] = False
    failed["summary"]["committed"] = 2
    failed["summary"]["hard_rejects"] = 1

    summary = aggregate(matrix, expected_combinations=15, sections_per_combo=3)

    assert summary["gate"] == "STAGE1_PASS"
    assert summary["committed"] == 44
    assert summary["hard_rejects"] == 1
    assert summary["gate_checks"]["committed_at_least_43_of_45"] is True


def test_stage1_aggregate_fails_below_43_commits() -> None:
    matrix = deepcopy(_matrix())
    for combination, section in ((0, 0), (1, 1), (2, 2)):
        failed = matrix["combinations"][combination]
        failed["sections"][section]["committed"] = False
        failed["sections"][section]["narrative_contract_pass"] = False
        failed["summary"]["committed"] = 2
        failed["summary"]["hard_rejects"] = 1

    summary = aggregate(matrix, expected_combinations=15, sections_per_combo=3)

    assert summary["gate"] == "STAGE1_FAIL"
    assert summary["committed"] == 42
    assert summary["gate_checks"]["committed_at_least_43_of_45"] is False


def test_mini_matrix_aggregate_uses_14_of_15_gate() -> None:
    matrix = _matrix()
    matrix["combinations"] = matrix["combinations"][:5]
    failed = matrix["combinations"][0]
    failed["sections"][0]["committed"] = False
    failed["sections"][0]["narrative_contract_pass"] = False
    failed["summary"]["committed"] = 2
    failed["summary"]["hard_rejects"] = 1

    summary = aggregate(matrix, expected_combinations=5, sections_per_combo=3)

    assert summary["gate"] == "MINI_MATRIX_PASS"
    assert summary["committed"] == 14
    assert summary["contract_pass_rate"] == 0.9333
    assert summary["length_in_range_rate"] == 1.0


def test_mini_matrix_fails_when_fewer_than_93pct_are_900_to_1100() -> None:
    matrix = _matrix()
    matrix["combinations"] = matrix["combinations"][:5]
    matrix["combinations"][0]["sections"][0]["narrative_length"] = 1101
    matrix["combinations"][1]["sections"][0]["narrative_length"] = 899

    summary = aggregate(matrix, expected_combinations=5, sections_per_combo=3)

    assert summary["length_in_range_count"] == 13
    assert summary["length_in_range_rate"] == 0.8667
    assert summary["gate_checks"]["length_900_1100_at_least_93pct"] is False
    assert summary["gate"] == "MINI_MATRIX_FAIL"


def test_stage1_aggregate_fails_on_unsafe_committed_proposals() -> None:
    matrix = deepcopy(_matrix())
    matrix["combinations"][0]["sections"][0][
        "illegal_thread_change_commits"
    ] = 1
    matrix["combinations"][1]["sections"][0][
        "evidenceless_state_delta_commits"
    ] = 1

    summary = aggregate(matrix, expected_combinations=15, sections_per_combo=3)

    assert summary["gate"] == "STAGE1_FAIL"
    assert summary["gate_checks"]["illegal_thread_change_commits_zero"] is False
    assert summary["gate_checks"]["evidenceless_state_delta_commits_zero"] is False


def test_stage1_combo_integrity_checks_revision_chain_and_story_bible() -> None:
    report = deepcopy(_matrix()["combinations"][0])
    assert _combo_integrity(report) == []

    report["sections"][1]["canonical_revision_before"] = 9
    report["sections"][2]["story_bible_revision"] = 2

    problems = _combo_integrity(report)
    assert "canonical_revision_chain_broken" in problems
    assert "canonical_revision_jump" in problems
    assert "story_bible_revision_changed" in problems


def test_stage1_analyzer_flattens_matrix_and_renders_all_sections() -> None:
    matrix = _matrix()
    matrix["summary"] = aggregate(
        matrix,
        expected_combinations=15,
        sections_per_combo=3,
    )

    analysis = analyze(matrix)
    markdown = render_markdown(analysis)

    assert analysis["gate"] == "STAGE1_PASS"
    assert analysis["metrics"]["attempted"] == 45
    assert set(analysis["by_theme"]) == {
        "reality_mystery",
        "action_conflict",
        "warm_relationship",
    }
    assert len(analysis["by_style"]) == 5
    assert (
        analysis["continuity"]["first_to_third_memory_selection_rate"]
        == 1.0
    )
    assert markdown.count("| reality_mystery |") >= 15
    assert "## 45-section detail" in markdown


def test_real_resume_uses_new_request_id_after_provider_failure() -> None:
    failures = [
        {"section": 2, "attempt": 1},
        {"section": 1, "attempt": 1},
        {"section": 2, "attempt": 2},
    ]

    request_id, prior_failures = _request_id(2, failures)

    assert request_id == "section_0002_retry_02"
    assert prior_failures == 2
