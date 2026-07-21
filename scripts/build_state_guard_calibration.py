"""Build the Phase 8 loss-aware StateGuard calibration dataset.

No LLM is called.  Phase 7 rejects remain ambiguous because their complete rejected
drafts are unavailable.  Review records are explicitly Codex-assisted rubric passes,
not human labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


ERROR_TYPES = [
    "event_endpoint_unfulfilled",
    "location_mismatch",
    "item_holder_conflict",
    "item_condition_conflict",
    "knowledge_leak",
    "ledger_missing_field",
    "ledger_wrong_type",
    "evidence_extraction_failure",
    "reasonable_omission",
    "new_ungrounded_fact",
    "repair_fact_change",
]


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def repair_review_text(text: str) -> str:
    """Decode known Latin-1/CP1252→GBK mojibake only when CJK score improves."""
    original_score = sum("\u3400" <= char <= "\u9fff" for char in text)
    best = text
    best_score = original_score
    for encoding in ("cp1252", "latin1"):
        try:
            candidate = text.encode(encoding).decode("gbk")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        score = sum("\u3400" <= char <= "\u9fff" for char in candidate)
        if score > best_score:
            best = candidate
            best_score = score
    return best


def _decode_review_value(value: Any) -> Any:
    if isinstance(value, str):
        return repair_review_text(value)
    if isinstance(value, list):
        return [_decode_review_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _decode_review_value(item) for key, item in value.items()}
    return value


def _phase7_error_types(case: dict[str, Any]) -> list[str]:
    if case["recorded_final_decision"] == "accept":
        return []
    before = case.get("before") or {}
    errors: list[str] = []
    if before.get("reported_safe") and not before.get("safe"):
        errors.append("evidence_extraction_failure")
    if before.get("event_fulfillment_conflicts"):
        errors.append("event_endpoint_unfulfilled")
    ledger_conflicts = before.get("ledger_conflicts") or []
    conflict_paths = " ".join(
        str(item.get("path") or "")
        for item in ledger_conflicts
        if isinstance(item, dict)
    )
    if ".location" in conflict_paths:
        errors.append("location_mismatch")
    if ".holder" in conflict_paths:
        errors.append("item_holder_conflict")
    if ".condition" in conflict_paths or ".status" in conflict_paths:
        errors.append("item_condition_conflict")
    if before.get("entity_grounding_conflicts"):
        errors.append("new_ungrounded_fact")
    if any(
        (stage or {}).get("fact_changes_from_original")
        for stage in (case.get("after"), case.get("after_retry"))
    ):
        errors.append("repair_fact_change")
    if not errors:
        errors.append("evidence_extraction_failure")
    return [error for error in ERROR_TYPES if error in set(errors)]


def _review(
    *,
    reviewer_id: str,
    decision: str,
    error_types: list[str],
    rationale: str,
    confidence: str,
) -> dict[str, Any]:
    return {
        "reviewer_id": reviewer_id,
        "reviewer_kind": "codex_assisted_rubric_pass",
        "human_reviewer": False,
        "expected_final_decision": decision,
        "error_types": error_types,
        "confidence": confidence,
        "rationale": rationale,
    }


def _phase7_case(case: dict[str, Any]) -> dict[str, Any]:
    recorded = case["recorded_final_decision"]
    complete = case["completeness"]
    if recorded == "accept":
        expected = "accept"
        confidence = "medium"
        rationale_a = (
            "Trace-first pass: persisted source text exists, all recorded checks "
            "passed and the final output was accepted."
        )
        rationale_b = (
            "Completeness-first pass: accepted full text remains available in the "
            "hashed source; no recorded contradiction survived."
        )
    else:
        expected = "ambiguous"
        confidence = "low"
        rationale_a = (
            "Trace-first pass: production rejected this case, but the complete "
            "rejected draft is absent, so the trace cannot establish ground truth."
        )
        rationale_b = (
            "Completeness-first pass: verifier excerpts and repair declarations are "
            "insufficient to rule out omitted supporting prose."
        )
    error_types = _phase7_error_types(case)
    before = case.get("before") or {}
    repair_attempted = bool(case.get("repair_declared") or case.get("after"))
    fact_change_lists = [
        (stage or {}).get("fact_changes_from_original") or []
        for stage in (case.get("after"), case.get("after_retry"))
    ]
    repair_fact_preserved = (
        all(not changes for changes in fact_change_lists)
        if repair_attempted
        else None
    )
    reviews = [
        _review(
            reviewer_id="codex_trace_pass_a",
            decision=expected,
            error_types=error_types,
            rationale=rationale_a,
            confidence=confidence,
        ),
        _review(
            reviewer_id="codex_completeness_pass_b",
            decision=expected,
            error_types=error_types,
            rationale=rationale_b,
            confidence=confidence,
        ),
    ]
    return {
        "case_id": f"phase7:{case['case_id']}",
        "source_type": "phase7_recorded_trace",
        "source_reference": case["source"],
        "theme": case.get("theme", ""),
        "style": case.get("style", ""),
        "tick": case.get("tick", 0),
        "review_material": _decode_review_value(
            {
                "required_events": case.get("required_events") or [],
                "evidence_excerpts": case.get("evidence_excerpts") or [],
                "event_checks": before.get("event_checks") or [],
                "event_fulfillment_conflicts": (
                    before.get("event_fulfillment_conflicts") or []
                ),
                "ledger_conflicts": before.get("ledger_conflicts") or [],
                "reason": before.get("reason") or "",
            }
        ),
        "completeness": complete,
        "recorded_signals": {
            "verifier_reported_safe": bool(before.get("reported_safe")),
            "deterministic_gate_passed": bool(before.get("safe")),
            "combined_final_accepted": recorded == "accept",
            "repair_attempted": repair_attempted,
            "repair_succeeded": bool(recorded == "accept" and repair_attempted),
            "repair_fact_preserved": repair_fact_preserved,
        },
        "recorded_final_decision": recorded,
        "reviews": reviews,
        "adjudication": {
            "status": "provisional_agreement",
            "expected_final_decision": expected,
            "error_types": error_types,
            "human_reviewed": False,
        },
    }


def _manual_case(case: dict[str, Any], source: dict[str, str]) -> dict[str, Any]:
    decision = case["expected_final_decision"]
    errors = list(case.get("error_types") or [])
    reviews = [
        _review(
            reviewer_id="codex_trace_pass_a",
            decision=decision,
            error_types=errors,
            rationale=str(case["rationale_a"]),
            confidence="high" if decision != "ambiguous" else "medium",
        ),
        _review(
            reviewer_id="codex_completeness_pass_b",
            decision=decision,
            error_types=errors,
            rationale=str(case["rationale_b"]),
            confidence="high" if decision != "ambiguous" else "medium",
        ),
    ]
    review_material = {
        key: value
        for key, value in case.items()
        if key
        not in {
            "expected_final_decision",
            "error_types",
            "rationale_a",
            "rationale_b",
        }
    }
    return {
        "case_id": f"manual:{case['case_id']}",
        "source_type": "minimal_synthetic_counterexample",
        "source_reference": source,
        "theme": "synthetic_minimal",
        "style": "style_neutral",
        "tick": 0,
        "review_material": review_material,
        "completeness": {
            "accepted_text_available_in_source": True,
            "accepted_text_copied_to_conversion": True,
            "rejected_draft_available": True,
            "full_repair_text_available": bool(case.get("repair_excerpt")),
            "verifier_payloads_available": False,
            "decision_trace_available": False,
        },
        "recorded_signals": {
            "verifier_reported_safe": None,
            "deterministic_gate_passed": None,
            "combined_final_accepted": None,
            "repair_attempted": bool(case.get("repair_excerpt")),
            "repair_succeeded": None,
            "repair_fact_preserved": (
                False if case.get("repair_excerpt") else None
            ),
        },
        "recorded_final_decision": None,
        "reviews": reviews,
        "adjudication": {
            "status": "provisional_agreement",
            "expected_final_decision": decision,
            "error_types": errors,
            "human_reviewed": False,
        },
    }


def build_dataset(recorded_path: Path, manual_path: Path) -> dict[str, Any]:
    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    manual = json.loads(manual_path.read_text(encoding="utf-8"))
    manual_source = {
        "filename": manual_path.name,
        "sha256": _file_sha256(manual_path),
    }
    cases = [_phase7_case(case) for case in recorded["cases"]]
    cases.extend(_manual_case(case, manual_source) for case in manual["cases"])
    cases.sort(key=lambda case: case["case_id"])
    if len({case["case_id"] for case in cases}) != len(cases):
        raise ValueError("calibration case IDs must be unique")

    decisions = Counter(
        case["adjudication"]["expected_final_decision"] for case in cases
    )
    error_counts = Counter(
        error
        for case in cases
        for error in case["adjudication"]["error_types"]
    )
    agreement_count = sum(
        len(case["reviews"]) == 2
        and case["reviews"][0]["expected_final_decision"]
        == case["reviews"][1]["expected_final_decision"]
        and case["reviews"][0]["error_types"]
        == case["reviews"][1]["error_types"]
        for case in cases
    )
    result = {
        "schema_version": "state-guard-calibration-v1",
        "label_provenance": {
            "kind": "codex_assisted_dual_rubric_pass",
            "human_reviewed": False,
            "warning": (
                "Provisional labels are reproducible review aids, not independent "
                "human ground truth."
            ),
        },
        "source_artifacts": [
            {
                "filename": recorded_path.name,
                "sha256": _file_sha256(recorded_path),
                "cases_sha256": recorded.get("cases_sha256", ""),
            },
            manual_source,
        ],
        "taxonomy": ERROR_TYPES,
        "summary": {
            "case_count": len(cases),
            "phase7_case_count": len(recorded["cases"]),
            "synthetic_case_count": len(manual["cases"]),
            "decision_counts": {
                key: decisions.get(key, 0)
                for key in ("accept", "reject", "ambiguous")
            },
            "decisive_case_count": (
                decisions.get("accept", 0) + decisions.get("reject", 0)
            ),
            "double_reviewed_count": len(cases),
            "review_agreement_count": agreement_count,
            "human_reviewed_count": 0,
            "error_type_counts": {
                error: error_counts.get(error, 0) for error in ERROR_TYPES
            },
        },
        "cases": cases,
    }
    result["dataset_sha256"] = _stable_sha256(cases)
    return result


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp.json", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.remove(temp_name)
        except OSError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recorded", help="Phase 7 converted guard cases")
    parser.add_argument("manual", help="Minimal curated cases JSON")
    parser.add_argument("--out", required=True, help="Calibration dataset JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_dataset(Path(args.recorded), Path(args.manual))
    write_json(Path(args.out).resolve(), result)
    print(
        json.dumps(
            {
                "out": str(Path(args.out).resolve()),
                "cases": result["summary"]["case_count"],
                "decisions": result["summary"]["decision_counts"],
                "human_reviewed": result["summary"]["human_reviewed_count"],
                "dataset_sha256": result["dataset_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
