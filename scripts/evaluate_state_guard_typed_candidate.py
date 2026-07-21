"""Evaluate the offline typed StateGuard candidate on complete replay traces."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _REPO_ROOT / "backend"
for _path in (str(_BACKEND), str(_REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from narrative.state_guard_typed_candidate import (  # noqa: E402
    evaluate_typed_candidate,
)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _wilson(successes: int, total: int) -> list[float] | None:
    if total <= 0:
        return None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return [round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)]


def _confusion(rows: list[tuple[str, str]]) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    for expected, predicted in rows:
        expected_reject = expected == "reject"
        predicted_reject = predicted == "reject"
        if expected_reject and predicted_reject:
            tp += 1
        elif not expected_reject and predicted_reject:
            fp += 1
        elif not expected_reject and not predicted_reject:
            tn += 1
        else:
            fn += 1
    precision_denom = tp + fp
    reject_denom = tp + fn
    accept_denom = fp + tn
    total = len(rows)
    return {
        "positive_class": "reject",
        "evaluated_cases": total,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "metrics": {
            "precision": _ratio(tp, precision_denom),
            "recall": _ratio(tp, reject_denom),
            "false_positive_rate": _ratio(fp, accept_denom),
            "false_negative_rate": _ratio(fn, reject_denom),
            "accuracy": _ratio(tp + tn, total),
        },
        "wilson_95": {
            "precision": _wilson(tp, precision_denom),
            "recall": _wilson(tp, reject_denom),
            "false_positive_rate": _wilson(fp, accept_denom),
            "false_negative_rate": _wilson(fn, reject_denom),
            "accuracy": _wilson(tp + tn, total),
        },
    }


def _source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def build_typed_candidate_report(
    phase8_dataset_path: Path,
    phase8_report_path: Path,
    replay_paths: list[Path],
) -> dict[str, Any]:
    phase8_dataset = json.loads(phase8_dataset_path.read_text(encoding="utf-8"))
    phase8_report = json.loads(phase8_report_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    error_counts: Counter[str] = Counter()
    for replay_path in replay_paths:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        for case in replay.get("cases") or []:
            trace = (case.get("ticks") or [{}])[-1].get("guard_trace")
            if not isinstance(trace, dict):
                raise ValueError(f"{case.get('fixture_id')} has no Guard trace")
            expected = (case.get("expectations") or {}).get("expected_acceptance")
            if expected not in {"accept", "reject"}:
                raise ValueError(f"{case.get('fixture_id')} is not decisive")
            expected_error_types = list(case.get("expected_error_types") or [])
            if expected == "reject":
                error_counts.update(expected_error_types)
            candidate = evaluate_typed_candidate(trace).model_dump(mode="json")
            baseline = str(trace.get("final_decision") or "")
            if baseline not in {"accept", "reject"}:
                raise ValueError(f"{case.get('fixture_id')} lacks baseline decision")
            rows.append(
                {
                    "fixture_id": case.get("fixture_id"),
                    "expected_final_decision": expected,
                    "expected_error_types": expected_error_types,
                    "baseline_decision": baseline,
                    "typed_candidate": candidate,
                    "fallback_preserving_decision": (
                        baseline if candidate["decision"] == "abstain" else candidate["decision"]
                    ),
                    "trace_schema_version": trace.get("schema_version"),
                    "trace_payload_complete": not bool(
                        (trace.get("payload_completeness") or {}).get("missing_fields")
                    ),
                }
            )

    decisive_new = len(rows)
    covered_rows = [
        row for row in rows if row["typed_candidate"]["decision"] != "abstain"
    ]
    baseline_metrics = _confusion(
        [(row["expected_final_decision"], row["baseline_decision"]) for row in rows]
    )
    typed_conditional = _confusion(
        [
            (row["expected_final_decision"], row["typed_candidate"]["decision"])
            for row in covered_rows
        ]
    )
    fallback_metrics = _confusion(
        [
            (row["expected_final_decision"], row["fallback_preserving_decision"])
            for row in rows
        ]
    )
    expected_rejects = sum(row["expected_final_decision"] == "reject" for row in rows)
    candidate_detected_rejects = sum(
        row["expected_final_decision"] == "reject"
        and row["typed_candidate"]["decision"] == "reject"
        for row in rows
    )
    abstain_count = decisive_new - len(covered_rows)
    coverage = _ratio(len(covered_rows), decisive_new)
    abstain_rate = _ratio(abstain_count, decisive_new)
    effective_recall = _ratio(candidate_detected_rejects, expected_rejects)

    phase8_summary = phase8_dataset["summary"]
    phase8_combined = phase8_report["quality_metrics"]["combined_final_decision"]
    signal_accepts = int(phase8_combined["labeled_accept_cases"]) + sum(
        row["expected_final_decision"] == "accept" for row in rows
    )
    signal_rejects = sum(row["expected_final_decision"] == "reject" for row in rows)
    combined_total = int(phase8_summary["case_count"]) + decisive_new
    combined_decisive = int(phase8_summary["decisive_case_count"]) + decisive_new
    combined_ambiguous = int(phase8_summary["decision_counts"]["ambiguous"])
    categories_at_least_three = sorted(
        code for code, count in error_counts.items() if count >= 3
    )
    repair_rows = [
        row for row in rows if "repair_fact_change" in row["expected_error_types"]
    ]
    repair_rejected = sum(
        row["typed_candidate"]["decision"] == "reject" for row in repair_rows
    )

    sample_gates = {
        "decisive_cases": {
            "value": combined_decisive,
            "minimum": 50,
            "passed": combined_decisive >= 50,
        },
        "signal_backed_rejects": {
            "value": signal_rejects,
            "minimum": 12,
            "passed": signal_rejects >= 12,
        },
        "signal_backed_accepts": {
            "value": signal_accepts,
            "minimum": 20,
            "passed": signal_accepts >= 20,
        },
        "typed_candidate_coverage": {
            "value": coverage,
            "minimum": 0.70,
            "passed": coverage is not None and coverage >= 0.70,
        },
        "hard_negative_categories": {
            "value": len(categories_at_least_three),
            "minimum": 6,
            "passed": len(categories_at_least_three) >= 6,
        },
        "independently_reviewed_decisive_cases": {
            "value": 0,
            "minimum": 20,
            "passed": False,
        },
    }
    quality_gates = {
        "fallback_hard_contradiction_recall_not_below_baseline": (
            fallback_metrics["metrics"]["recall"]
            >= baseline_metrics["metrics"]["recall"]
        ),
        "fallback_hard_contradiction_precision_at_least_0_90": (
            fallback_metrics["metrics"]["precision"] is not None
            and fallback_metrics["metrics"]["precision"] >= 0.90
        ),
        "fallback_false_positive_rate_not_above_baseline": (
            fallback_metrics["metrics"]["false_positive_rate"]
            <= baseline_metrics["metrics"]["false_positive_rate"]
        ),
        "typed_abstain_rate_at_most_0_30": (
            abstain_rate is not None and abstain_rate <= 0.30
        ),
        "repair_fact_change_preservation_not_below_baseline": (
            repair_rejected == len(repair_rows)
        ),
    }
    gate_reasons = [
        f"{name} gate failed: {gate['value']} < {gate['minimum']}"
        for name, gate in sample_gates.items()
        if not gate["passed"]
    ]
    gate_reasons.extend(
        f"quality gate failed: {name}"
        for name, passed in quality_gates.items()
        if not passed
    )
    report = {
        "schema_version": "state-guard-typed-candidate-evaluation-v1",
        "candidate_runtime_integration": False,
        "candidate_default_enabled": False,
        "canonical_fact_consumer_enabled": False,
        "sources": [
            {
                "filename": phase8_dataset_path.name,
                "sha256": _source_hash(phase8_dataset_path),
            },
            {
                "filename": phase8_report_path.name,
                "sha256": _source_hash(phase8_report_path),
            },
            *[
                {"filename": path.name, "sha256": _source_hash(path)}
                for path in replay_paths
            ],
        ],
        "dataset": {
            "combined_case_count": combined_total,
            "combined_decisive_case_count": combined_decisive,
            "combined_ambiguous_count": combined_ambiguous,
            "combined_ambiguous_rate": _ratio(combined_ambiguous, combined_total),
            "signal_backed_accepts": signal_accepts,
            "signal_backed_rejects": signal_rejects,
            "typed_evaluation_case_count": decisive_new,
            "typed_covered_count": len(covered_rows),
            "typed_abstain_count": abstain_count,
            "typed_candidate_coverage": coverage,
            "typed_candidate_coverage_wilson_95": _wilson(
                len(covered_rows), decisive_new
            ),
            "typed_candidate_abstain_rate": abstain_rate,
            "typed_candidate_abstain_wilson_95": _wilson(
                abstain_count, decisive_new
            ),
            "hard_negative_error_type_counts": dict(sorted(error_counts.items())),
            "hard_negative_categories_with_at_least_3_cases": categories_at_least_three,
        },
        "baseline_metrics": baseline_metrics,
        "typed_candidate_conditional_metrics": typed_conditional,
        "typed_candidate_abstain_aware": {
            "hard_contradictions_detected": candidate_detected_rejects,
            "hard_contradiction_count": expected_rejects,
            "effective_recall_treating_abstain_as_not_detected": effective_recall,
            "wilson_95": _wilson(candidate_detected_rejects, expected_rejects),
            "warning": (
                "Conditional confusion excludes abstentions. This effective recall "
                "shows the standalone candidate's unresolved hard negatives."
            ),
        },
        "fallback_preserving_metrics": fallback_metrics,
        "repair_fact_change": {
            "case_count": len(repair_rows),
            "candidate_reject_count": repair_rejected,
        },
        "probable_false_positives_reduced": (
            baseline_metrics["confusion"]["fp"]
            - fallback_metrics["confusion"]["fp"]
        ),
        "cases": rows,
        "behavior_gate": {
            "sample_gates": sample_gates,
            "quality_gates": quality_gates,
            "decision": "BLOCK_BEHAVIOR_CANDIDATE",
            "behavior_change_allowed": False,
            "reasons": gate_reasons,
            "next_iterations_blocked": [23, 24, 25],
        },
        "cost": {
            "fixture_transport_calls": 0,
            "provider_calls": 0,
            "model_tokens": None,
            "judge_tokens": None,
        },
    }
    report["report_sha256"] = _stable_hash(report)
    return report


def _show(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def render_markdown(report: dict[str, Any]) -> str:
    dataset = report["dataset"]
    baseline = report["baseline_metrics"]["metrics"]
    conditional = report["typed_candidate_conditional_metrics"]["metrics"]
    fallback = report["fallback_preserving_metrics"]["metrics"]
    lines = [
        "# Phase 9 typed StateGuard candidate evaluation",
        "",
        "- Runtime integration: disabled",
        "- CanonicalFact consumer: disabled",
        f"- Combined dataset: {dataset['combined_case_count']} total / "
        f"{dataset['combined_decisive_case_count']} decisive / "
        f"{dataset['combined_ambiguous_count']} ambiguous",
        f"- Typed coverage: {dataset['typed_covered_count']}/"
        f"{dataset['typed_evaluation_case_count']} "
        f"({_show(dataset['typed_candidate_coverage'])})",
        f"- Abstain: {dataset['typed_abstain_count']}/"
        f"{dataset['typed_evaluation_case_count']} "
        f"({_show(dataset['typed_candidate_abstain_rate'])})",
        "",
        "## Reject-positive metrics",
        "",
        "| Decision path | Precision | Recall | FPR | FNR | Accuracy |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| Baseline | {_show(baseline['precision'])} | {_show(baseline['recall'])} | "
        f"{_show(baseline['false_positive_rate'])} | "
        f"{_show(baseline['false_negative_rate'])} | {_show(baseline['accuracy'])} |",
        f"| Typed covered cases | {_show(conditional['precision'])} | "
        f"{_show(conditional['recall'])} | {_show(conditional['false_positive_rate'])} | "
        f"{_show(conditional['false_negative_rate'])} | {_show(conditional['accuracy'])} |",
        f"| Typed + baseline fallback | {_show(fallback['precision'])} | "
        f"{_show(fallback['recall'])} | {_show(fallback['false_positive_rate'])} | "
        f"{_show(fallback['false_negative_rate'])} | {_show(fallback['accuracy'])} |",
        "",
        "Conditional metrics exclude abstentions. Standalone abstain-aware hard-error "
        f"recall is {_show(report['typed_candidate_abstain_aware']['effective_recall_treating_abstain_as_not_detected'])}.",
        "",
        "## Behavior gate",
        "",
        f"Decision: `{report['behavior_gate']['decision']}`",
        "",
        *[f"- {reason}" for reason in report["behavior_gate"]["reasons"]],
        "",
        "Iterations 23–25 remain blocked. No production decision, feature flag or "
        "CanonicalFact consumer was added.",
        "",
        f"Report SHA-256: `{report['report_sha256']}`",
        "",
    ]
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
    parser.add_argument("--phase8-dataset", required=True)
    parser.add_argument("--phase8-report", required=True)
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_typed_candidate_report(
        Path(args.phase8_dataset).resolve(),
        Path(args.phase8_report).resolve(),
        [Path(value).resolve() for value in args.reports],
    )
    _atomic_write(
        Path(args.out_json).resolve(),
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write(Path(args.out_md).resolve(), render_markdown(report))
    print(
        json.dumps(
            {
                "coverage": report["dataset"]["typed_candidate_coverage"],
                "abstain": report["dataset"]["typed_candidate_abstain_rate"],
                "decision": report["behavior_gate"]["decision"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
