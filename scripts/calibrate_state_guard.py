"""Compute coverage-aware StateGuard calibration metrics without LLM calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


SIGNALS = {
    "verifier_reported_safe": "verifier_reported_safe",
    "deterministic_evidence_gate": "deterministic_gate_passed",
    "combined_final_decision": "combined_final_accepted",
}


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _confusion(
    rows: list[tuple[str, bool]],
    *,
    total_decisive: int,
) -> dict[str, Any]:
    # Positive class is a required rejection / unsafe case.
    tp = fp = tn = fn = 0
    for expected, predicted_accept in rows:
        expected_reject = expected == "reject"
        predicted_reject = not predicted_accept
        if expected_reject and predicted_reject:
            tp += 1
        elif not expected_reject and predicted_reject:
            fp += 1
        elif not expected_reject and not predicted_reject:
            tn += 1
        else:
            fn += 1
    evaluated = len(rows)
    actual_rejects = tp + fn
    actual_accepts = tn + fp
    predicted_rejects = tp + fp
    metrics = {
        "precision": _ratio(tp, predicted_rejects),
        "recall": _ratio(tp, actual_rejects),
        "false_positive_rate": _ratio(fp, actual_accepts),
        "false_negative_rate": _ratio(fn, actual_rejects),
        "accuracy": _ratio(tp + tn, evaluated),
    }
    undefined = {
        key: reason
        for key, value, reason in (
            (
                "precision",
                metrics["precision"],
                "no predicted rejects in evaluated cases",
            ),
            (
                "recall",
                metrics["recall"],
                "no labeled rejects with this recorded signal",
            ),
            (
                "false_positive_rate",
                metrics["false_positive_rate"],
                "no labeled accepts with this recorded signal",
            ),
            (
                "false_negative_rate",
                metrics["false_negative_rate"],
                "no labeled rejects with this recorded signal",
            ),
            (
                "accuracy",
                metrics["accuracy"],
                "no decisive cases with this recorded signal",
            ),
        )
        if value is None
    }
    return {
        "positive_class": "reject",
        "evaluated_cases": evaluated,
        "total_decisive_cases": total_decisive,
        "coverage": _ratio(evaluated, total_decisive),
        "labeled_reject_cases": actual_rejects,
        "labeled_accept_cases": actual_accepts,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "metrics": metrics,
        "undefined_metrics": undefined,
    }


def _quality_metric(
    cases: list[dict[str, Any]],
    signal_key: str,
    *,
    total_decisive: int,
) -> dict[str, Any]:
    rows: list[tuple[str, bool]] = []
    for case in cases:
        expected = case["adjudication"]["expected_final_decision"]
        signal = case["recorded_signals"].get(signal_key)
        if expected == "ambiguous" or not isinstance(signal, bool):
            continue
        rows.append((expected, signal))
    return _confusion(rows, total_decisive=total_decisive)


def _operational_metric(
    cases: list[dict[str, Any]], signal_key: str
) -> dict[str, Any]:
    rows: list[tuple[str, bool]] = []
    for case in cases:
        recorded = case.get("recorded_final_decision")
        signal = case["recorded_signals"].get(signal_key)
        if recorded not in {"accept", "reject"} or not isinstance(signal, bool):
            continue
        rows.append((recorded, signal))
    result = _confusion(rows, total_decisive=len(rows))
    result["ground_truth"] = False
    result["warning"] = (
        "Target is the recorded production outcome; this measures reproduction, "
        "not correctness."
    )
    return result


def build_report(dataset_path: Path) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    decision_counts = dataset["summary"]["decision_counts"]
    total_decisive = int(dataset["summary"]["decisive_case_count"])

    quality_metrics = {
        name: _quality_metric(cases, key, total_decisive=total_decisive)
        for name, key in SIGNALS.items()
    }
    quality_metrics["typed_ledger_candidate"] = {
        "status": "unavailable",
        "evaluated_cases": 0,
        "total_decisive_cases": total_decisive,
        "coverage": 0.0,
        "metrics": {
            "precision": None,
            "recall": None,
            "false_positive_rate": None,
            "false_negative_rate": None,
            "accuracy": None,
        },
        "undefined_metrics": {
            "all": (
                "Calibration cases contain typed ledger structure examples but no "
                "recorded typed-ledger final-decision signal."
            )
        },
    }

    phase7 = [
        case
        for case in cases
        if case["source_type"] == "phase7_recorded_trace"
    ]
    operational = {
        name: _operational_metric(phase7, key)
        for name, key in SIGNALS.items()
    }
    patterns = Counter(
        (
            case["recorded_signals"]["verifier_reported_safe"],
            case["recorded_signals"]["deterministic_gate_passed"],
            case["recorded_signals"]["combined_final_accepted"],
        )
        for case in phase7
    )
    attempts = [
        case
        for case in phase7
        if case["recorded_signals"]["repair_attempted"]
    ]
    repair_successes = sum(
        bool(case["recorded_signals"]["repair_succeeded"])
        for case in attempts
    )
    preserved = sum(
        case["recorded_signals"]["repair_fact_preserved"] is True
        for case in attempts
    )
    failure_taxonomy = {
        "phase7_signal_buckets": {
            "initial_accept": patterns.get((True, True, True), 0),
            "deterministic_reject_after_verifier_safe": patterns.get(
                (True, False, False), 0
            ),
            "verifier_and_deterministic_reject": patterns.get(
                (False, False, False), 0
            ),
            "repair_rescue_after_verifier_safe": patterns.get(
                (True, False, True), 0
            ),
            "repair_rescue_after_verifier_reject": patterns.get(
                (False, False, True), 0
            ),
        },
        "provisional_error_type_counts": dataset["summary"][
            "error_type_counts"
        ],
        "probable_evidence_false_negative_count": patterns.get(
            (True, False, False), 0
        ),
        "warning": (
            "The 31 verifier-safe/deterministic-reject cases are probable evidence "
            "failures, not confirmed false positives, because rejected drafts are "
            "missing."
        ),
    }
    repair = {
        "attempt_count": len(attempts),
        "success_count": repair_successes,
        "success_rate": _ratio(repair_successes, len(attempts)),
        "fact_preserved_count": preserved,
        "fact_preservation_rate": _ratio(preserved, len(attempts)),
        "fact_change_or_unknown_count": len(attempts) - preserved,
    }
    ambiguous_count = int(decision_counts["ambiguous"])
    signal_backed_labeled_rejects = max(
        metric["labeled_reject_cases"]
        for metric in quality_metrics.values()
        if metric.get("status") != "unavailable"
    )
    gate_reasons = []
    if total_decisive < 40:
        gate_reasons.append(
            f"only {total_decisive} decisive labels; minimum behavior gate is 40"
        )
    if signal_backed_labeled_rejects == 0:
        gate_reasons.append(
            "no labeled reject has recorded verifier/deterministic/combined signals"
        )
    if dataset["summary"]["human_reviewed_count"] == 0:
        gate_reasons.append("no label has independent human review")
    if quality_metrics["typed_ledger_candidate"]["evaluated_cases"] == 0:
        gate_reasons.append("typed-ledger candidate decision coverage is zero")

    report = {
        "schema_version": "state-guard-calibration-report-v1",
        "dataset": {
            "filename": dataset_path.name,
            "dataset_sha256": dataset["dataset_sha256"],
            "case_count": len(cases),
            "decision_counts": decision_counts,
            "decisive_case_count": total_decisive,
            "ambiguous_count": ambiguous_count,
            "ambiguous_rate": _ratio(ambiguous_count, len(cases)),
            "human_reviewed_count": dataset["summary"]["human_reviewed_count"],
        },
        "metric_semantics": {
            "positive_class": "reject",
            "ambiguous_policy": "excluded_from_quality_confusion",
            "null_policy": "unsupported denominators remain null",
        },
        "quality_metrics": quality_metrics,
        "operational_reproduction": operational,
        "failure_taxonomy": failure_taxonomy,
        "repair": repair,
        "behavior_gate": {
            "can_run_iteration16": False,
            "decision": "BLOCK_BEHAVIOR_CANDIDATE",
            "reasons": gate_reasons,
        },
        "production_acceptance_logic_changed": False,
    }
    report["report_sha256"] = hashlib.sha256(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return report


def render_markdown(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    lines = [
        "# StateGuard calibration report",
        "",
        f"- Dataset: `{dataset['filename']}`",
        f"- Cases: {dataset['case_count']} (decisive {dataset['decisive_case_count']}, "
        f"ambiguous {dataset['ambiguous_count']} / {dataset['ambiguous_rate']:.3f})",
        f"- Human-reviewed: {dataset['human_reviewed_count']}",
        "- Positive class: reject; ambiguous cases are excluded.",
        "",
        "## Provisional-label quality metrics",
        "",
        "| Signal | Coverage | TP | FP | TN | FN | Precision | Recall | FPR | FNR |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, metric in report["quality_metrics"].items():
        if metric.get("status") == "unavailable":
            lines.append(f"| {name} | 0 | — | — | — | — | — | — | — | — |")
            continue
        confusion = metric["confusion"]
        values = metric["metrics"]

        def show(value: float | None) -> str:
            return "—" if value is None else f"{value:.3f}"

        lines.append(
            f"| {name} | {show(metric['coverage'])} | {confusion['tp']} | "
            f"{confusion['fp']} | {confusion['tn']} | {confusion['fn']} | "
            f"{show(values['precision'])} | {show(values['recall'])} | "
            f"{show(values['false_positive_rate'])} | "
            f"{show(values['false_negative_rate'])} |"
        )
    lines.extend(
        [
            "",
            "Undefined values are intentionally not coerced. There is no labeled "
            "reject with recorded signals, so hard-error recall cannot be measured.",
            "",
            "## Repair",
            "",
            f"- Attempts: {report['repair']['attempt_count']}",
            f"- Success: {report['repair']['success_count']} "
            f"({report['repair']['success_rate']:.3f})",
            f"- Fact preservation: {report['repair']['fact_preserved_count']} "
            f"({report['repair']['fact_preservation_rate']:.3f})",
            "",
            "## Behavior gate",
            "",
            f"Decision: `{report['behavior_gate']['decision']}`",
            "",
        ]
    )
    lines.extend(f"- {reason}" for reason in report["behavior_gate"]["reasons"])
    lines.extend(
        [
            "",
            "Operational reproduction targets recorded production outcomes and is "
            "not ground-truth quality evidence.",
            "",
            f"Report SHA-256: `{report['report_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="Calibration dataset JSON")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(Path(args.dataset))
    _atomic_write(
        Path(args.out_json).resolve(),
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write(Path(args.out_md).resolve(), render_markdown(report))
    print(
        json.dumps(
            {
                "out_json": str(Path(args.out_json).resolve()),
                "out_md": str(Path(args.out_md).resolve()),
                "decision": report["behavior_gate"]["decision"],
                "report_sha256": report["report_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
