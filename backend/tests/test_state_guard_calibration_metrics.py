from __future__ import annotations

import json
from pathlib import Path

from scripts.calibrate_state_guard import build_report, render_markdown


ROOT = Path(__file__).resolve().parents[2]
DATASET = (
    ROOT
    / "docs"
    / "iter"
    / "state_guard_calibration"
    / "phase8-state-guard-calibration-v1.json"
)
REPORT = DATASET.with_name("phase8-state-guard-calibration-report-v1.json")
MARKDOWN = DATASET.with_name("phase8-state-guard-calibration-report-v1.md")


def test_quality_metrics_exclude_ambiguous_and_leave_recall_undefined() -> None:
    report = build_report(DATASET)
    metrics = report["quality_metrics"]

    verifier = metrics["verifier_reported_safe"]
    assert verifier["evaluated_cases"] == 20
    assert verifier["total_decisive_cases"] == 34
    assert verifier["coverage"] == 0.588235
    assert verifier["confusion"] == {"tp": 0, "fp": 1, "tn": 19, "fn": 0}
    assert verifier["metrics"] == {
        "precision": 0.0,
        "recall": None,
        "false_positive_rate": 0.05,
        "false_negative_rate": None,
        "accuracy": 0.95,
    }
    assert "recall" in verifier["undefined_metrics"]

    deterministic = metrics["deterministic_evidence_gate"]
    assert deterministic["confusion"] == {
        "tp": 0,
        "fp": 4,
        "tn": 16,
        "fn": 0,
    }
    assert deterministic["metrics"]["false_positive_rate"] == 0.2
    assert deterministic["metrics"]["recall"] is None

    combined = metrics["combined_final_decision"]
    assert combined["confusion"] == {"tp": 0, "fp": 0, "tn": 20, "fn": 0}
    assert combined["metrics"]["precision"] is None
    assert combined["metrics"]["recall"] is None
    assert combined["metrics"]["false_positive_rate"] == 0.0

    typed = metrics["typed_ledger_candidate"]
    assert typed["status"] == "unavailable"
    assert typed["evaluated_cases"] == 0
    assert all(value is None for value in typed["metrics"].values())


def test_operational_reproduction_is_explicitly_not_ground_truth() -> None:
    report = build_report(DATASET)
    operational = report["operational_reproduction"]

    assert operational["verifier_reported_safe"]["confusion"] == {
        "tp": 5,
        "fp": 1,
        "tn": 19,
        "fn": 31,
    }
    assert operational["deterministic_evidence_gate"]["confusion"] == {
        "tp": 36,
        "fp": 4,
        "tn": 16,
        "fn": 0,
    }
    assert operational["combined_final_decision"]["metrics"]["accuracy"] == 1.0
    assert all(metric["ground_truth"] is False for metric in operational.values())
    assert all("not correctness" in metric["warning"] for metric in operational.values())


def test_failure_buckets_repair_rates_and_behavior_gate_are_auditable() -> None:
    report = build_report(DATASET)

    assert report["failure_taxonomy"]["phase7_signal_buckets"] == {
        "initial_accept": 16,
        "deterministic_reject_after_verifier_safe": 31,
        "verifier_and_deterministic_reject": 5,
        "repair_rescue_after_verifier_safe": 3,
        "repair_rescue_after_verifier_reject": 1,
    }
    assert report["repair"] == {
        "attempt_count": 40,
        "success_count": 4,
        "success_rate": 0.1,
        "fact_preserved_count": 32,
        "fact_preservation_rate": 0.8,
        "fact_change_or_unknown_count": 8,
    }
    gate = report["behavior_gate"]
    assert gate["can_run_iteration16"] is False
    assert gate["decision"] == "BLOCK_BEHAVIOR_CANDIDATE"
    assert len(gate["reasons"]) == 4
    assert report["production_acceptance_logic_changed"] is False


def test_calibration_report_and_markdown_are_reproducible() -> None:
    first = build_report(DATASET)
    second = build_report(DATASET)
    persisted = json.loads(REPORT.read_text(encoding="utf-8"))

    assert first == second == persisted
    assert first["report_sha256"] == (
        "b4d6f86a0c1b9c12c14ab5d82903317b4763185afd7fde549606c5c0c636dddc"
    )
    markdown = render_markdown(first)
    assert markdown == MARKDOWN.read_text(encoding="utf-8")
    assert "BLOCK_BEHAVIOR_CANDIDATE" in markdown
    assert "hard-error recall cannot be measured" in markdown
