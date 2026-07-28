"""Validate independent blind reviews, export disagreements, and freeze gold labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import tempfile
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


DECISIONS = ("accept", "reject", "ambiguous")
INDEPENDENT_REVIEWER_TYPES = {"human", "independent_model"}


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    decision: str
    error_types: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        if value not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        return value


class ReviewUsage(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider_calls: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    packet_id: str
    packet_sha256: str
    packet_hash: str = ""
    reviewer_id: str = Field(min_length=3, max_length=100)
    reviewer_type: str
    model_family: str = ""
    model_name: str = ""
    provider_name: str = ""
    review_started_at: str = ""
    review_finished_at: str = ""
    prompt_hash: str = ""
    temperature: float | None = None
    blind_key_accessed: bool = False
    review_input_files: list[str] = Field(default_factory=list)
    usage: ReviewUsage = Field(default_factory=ReviewUsage)
    raw_response_sha256: str = ""
    results: list[ReviewResult]

    @field_validator("schema_version")
    @classmethod
    def validate_schema(cls, value: str) -> str:
        if value not in {
            "state-guard-adjudication-review-v1",
            "state-guard-adjudication-review-v2",
        }:
            raise ValueError("unsupported review schema")
        return value

    @field_validator("reviewer_type")
    @classmethod
    def validate_reviewer_type(cls, value: str) -> str:
        allowed = {"human", "independent_model", "project_agent"}
        if value not in allowed:
            raise ValueError(f"reviewer_type must be one of {sorted(allowed)}")
        return value

    @model_validator(mode="after")
    def validate_phase10_metadata(self) -> "ReviewSubmission":
        if self.schema_version.endswith("-v1"):
            return self
        if self.packet_hash != self.packet_sha256:
            raise ValueError("packet_hash must match packet_sha256")
        required = {
            "model_family": self.model_family,
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "review_started_at": self.review_started_at,
            "review_finished_at": self.review_finished_at,
            "prompt_hash": self.prompt_hash,
        }
        missing = [name for name, value in required.items() if not value]
        if self.reviewer_type == "human":
            missing = [
                name
                for name in missing
                if name not in {"model_family", "model_name", "provider_name"}
            ]
        if missing:
            raise ValueError(f"missing Phase 10 review metadata: {missing}")
        try:
            started = datetime.fromisoformat(self.review_started_at.replace("Z", "+00:00"))
            finished = datetime.fromisoformat(self.review_finished_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("review timestamps must be ISO-8601") from exc
        if finished < started:
            raise ValueError("review_finished_at precedes review_started_at")
        if self.blind_key_accessed:
            raise ValueError("reviewer attests that the blind key was accessed")
        if not self.review_input_files:
            raise ValueError("review_input_files must be recorded")
        if any("key" in Path(value).name.casefold() for value in self.review_input_files):
            raise ValueError("review input filenames contain a key artifact")
        return self


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def cohens_kappa(left: list[str], right: list[str]) -> float | None:
    if len(left) != len(right):
        raise ValueError("reviewer decision vectors have different lengths")
    if not left:
        return None
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    expected = sum(
        (left.count(label) / len(left)) * (right.count(label) / len(right))
        for label in DECISIONS
    )
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return round((observed - expected) / (1.0 - expected), 6)


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _validate_hashed_payload(
    payload: dict[str, Any], hash_field: str, label: str
) -> str:
    without_hash = dict(payload)
    stored_hash = without_hash.pop(hash_field, None)
    if not stored_hash or stored_hash != _stable_hash(without_hash):
        raise ValueError(f"{label} hash mismatch")
    return str(stored_hash)


def _load_submission(path: Path) -> ReviewSubmission:
    return ReviewSubmission.model_validate_json(path.read_text(encoding="utf-8"))


def _validate_review_coverage(
    submission: ReviewSubmission,
    *,
    packet_id: str,
    packet_hash: str,
    expected_ids: set[str],
) -> dict[str, ReviewResult]:
    if submission.packet_id != packet_id:
        raise ValueError(f"review {submission.reviewer_id} packet_id mismatch")
    if submission.packet_sha256 != packet_hash:
        raise ValueError(f"review {submission.reviewer_id} packet hash mismatch")
    result_ids = [item.case_id for item in submission.results]
    if len(result_ids) != len(set(result_ids)):
        raise ValueError(f"review {submission.reviewer_id} has duplicate cases")
    if set(result_ids) != expected_ids:
        missing = sorted(expected_ids - set(result_ids))
        extra = sorted(set(result_ids) - expected_ids)
        raise ValueError(
            f"review {submission.reviewer_id} coverage mismatch; "
            f"missing={missing}, extra={extra}"
        )
    return {item.case_id: item for item in submission.results}


def _decision_confusion(
    left: dict[str, ReviewResult],
    right: dict[str, ReviewResult],
    case_ids: list[str],
) -> dict[str, dict[str, int]]:
    matrix = {
        left_label: {right_label: 0 for right_label in DECISIONS}
        for left_label in DECISIONS
    }
    for case_id in case_ids:
        matrix[left[case_id].decision][right[case_id].decision] += 1
    return matrix


def build_disagreement_packet(
    packet: dict[str, Any], disagreement_case_ids: list[str]
) -> dict[str, Any]:
    selected = {
        case["case_id"]: case
        for case in packet.get("cases") or []
        if case.get("case_id") in set(disagreement_case_ids)
    }
    cases = [selected[case_id] for case_id in disagreement_case_ids]
    disagreement = {
        "schema_version": "state-guard-adjudication-packet-v1",
        "packet_id": f"{packet['packet_id']}:disagreement-v1",
        "reviewer_instructions": (
            "这是独立分歧裁决包。请仅依据案例材料重新裁决；本包不含前两名"
            "审查者的答案、系统决定、fixture 标签或隐藏 key。"
        ),
        "case_count": len(cases),
        "cases": cases,
    }
    disagreement["packet_sha256"] = _stable_hash(disagreement)
    return disagreement


def _reviewer_summary(submission: ReviewSubmission) -> dict[str, Any]:
    confidences = [item.confidence for item in submission.results]
    return {
        "reviewer_id": submission.reviewer_id,
        "reviewer_type": submission.reviewer_type,
        "model_family": submission.model_family,
        "model_name": submission.model_name,
        "provider_name": submission.provider_name,
        "case_count": len(submission.results),
        "decisive_count": sum(item.decision != "ambiguous" for item in submission.results),
        "accept_count": sum(item.decision == "accept" for item in submission.results),
        "reject_count": sum(item.decision == "reject" for item in submission.results),
        "ambiguous_count": sum(item.decision == "ambiguous" for item in submission.results),
        "mean_confidence": round(statistics.fmean(confidences), 6) if confidences else None,
        "usage": submission.usage.model_dump(mode="json"),
        "blind_key_accessed": submission.blind_key_accessed,
        "provisional": submission.reviewer_type == "project_agent",
    }


def _confidence_distribution(submissions: list[ReviewSubmission]) -> dict[str, Any]:
    values = sorted(
        item.confidence for submission in submissions for item in submission.results
    )
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": len(values),
        "min": round(values[0], 6),
        "median": round(statistics.median(values), 6),
        "mean": round(statistics.fmean(values), 6),
        "max": round(values[-1], 6),
        "below_0_6": sum(value < 0.6 for value in values),
        "at_least_0_8": sum(value >= 0.8 for value in values),
    }


def _build_gold(
    *,
    packet: dict[str, Any],
    primary: list[ReviewSubmission],
    primary_by_id: dict[str, dict[str, ReviewResult]],
    adjudicator: ReviewSubmission | None,
    adjudicator_by_id: dict[str, ReviewResult] | None,
) -> dict[str, Any]:
    gold_cases: list[dict[str, Any]] = []
    first, second = primary
    for packet_case in packet.get("cases") or []:
        case_id = packet_case["case_id"]
        left = primary_by_id[first.reviewer_id][case_id]
        right = primary_by_id[second.reviewer_id][case_id]
        disagreement = left.decision != right.decision
        adjudicated = adjudicator_by_id.get(case_id) if adjudicator_by_id else None
        if disagreement and adjudicated is not None:
            final_label = adjudicated.decision
            confidence = adjudicated.confidence
            error_types = list(adjudicated.error_types)
            rationale = adjudicated.rationale
        elif disagreement:
            final_label = "ambiguous"
            confidence = round((left.confidence + right.confidence) / 2, 6)
            error_types = sorted(set(left.error_types) | set(right.error_types))
            rationale = "两名独立审查者决定不一致，等待第三方裁决。"
        else:
            final_label = left.decision
            confidence = round((left.confidence + right.confidence) / 2, 6)
            error_types = sorted(set(left.error_types) | set(right.error_types))
            rationale = f"独立审查一致：{left.rationale} / {right.rationale}"
        labels = [
            {
                "reviewer_id": first.reviewer_id,
                "reviewer_type": first.reviewer_type,
                "label": left.decision,
                "confidence": left.confidence,
                "error_types": list(left.error_types),
                "rationale": left.rationale,
            },
            {
                "reviewer_id": second.reviewer_id,
                "reviewer_type": second.reviewer_type,
                "label": right.decision,
                "confidence": right.confidence,
                "error_types": list(right.error_types),
                "rationale": right.rationale,
            },
        ]
        if adjudicator and adjudicated:
            labels.append(
                {
                    "reviewer_id": adjudicator.reviewer_id,
                    "reviewer_type": adjudicator.reviewer_type,
                    "label": adjudicated.decision,
                    "confidence": adjudicated.confidence,
                    "error_types": list(adjudicated.error_types),
                    "rationale": adjudicated.rationale,
                }
            )
        gold_cases.append(
            {
                "case_id": case_id,
                "final_label": final_label,
                "reviewer_labels": labels,
                "adjudication_required": disagreement,
                "adjudicator_label": adjudicated.decision if adjudicated else None,
                "confidence": confidence,
                "error_types": error_types,
                "rationale": rationale,
            }
        )
    summary = {
        "case_count": len(gold_cases),
        "accept_count": sum(case["final_label"] == "accept" for case in gold_cases),
        "reject_count": sum(case["final_label"] == "reject" for case in gold_cases),
        "ambiguous_count": sum(case["final_label"] == "ambiguous" for case in gold_cases),
        "decisive_count": sum(case["final_label"] != "ambiguous" for case in gold_cases),
        "adjudication_required_count": sum(case["adjudication_required"] for case in gold_cases),
        "adjudicated_count": sum(case["adjudicator_label"] is not None for case in gold_cases),
        "unresolved_disagreement_count": sum(
            case["adjudication_required"] and case["adjudicator_label"] is None
            for case in gold_cases
        ),
    }
    gold = {
        "schema_version": "state-guard-gold-labels-v1",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "reviewer_ids": [submission.reviewer_id for submission in primary],
        "adjudicator_id": adjudicator.reviewer_id if adjudicator else None,
        "summary": summary,
        "cases": gold_cases,
    }
    gold["gold_sha256"] = _stable_hash(gold)
    return gold


def _taxonomy_gate(gold_cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    case_sets = [set(case["error_types"]) for case in gold_cases]
    checks = {
        "endpoint_unfulfilled": sum("event_endpoint_unfulfilled" in values for values in case_sets),
        "location_mismatch": sum("location_mismatch" in values for values in case_sets),
        "item_holder_or_condition": sum(
            bool(values & {"item_holder_conflict", "item_condition_conflict"})
            for values in case_sets
        ),
        "knowledge_leak": sum("knowledge_leak" in values for values in case_sets),
        "repair_fact_change": sum("repair_fact_change" in values for values in case_sets),
        "reasonable_omission_or_evidence_failure": sum(
            bool(values & {"reasonable_omission", "evidence_extraction_failure"})
            for values in case_sets
        ),
    }
    return {
        name: {"value": value, "minimum": 2, "passed": value >= 2}
        for name, value in checks.items()
    }


def build_adjudication_report(
    packet_path: Path,
    key_path: Path,
    review_paths: list[Path],
    *,
    adjudicator_path: Path | None = None,
) -> dict[str, Any]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    if packet.get("schema_version") != "state-guard-adjudication-packet-v1":
        raise ValueError("unsupported adjudication packet schema")
    packet_hash = _validate_hashed_payload(packet, "packet_sha256", "adjudication packet")
    if key.get("packet_sha256") != packet_hash:
        raise ValueError("audit key is not bound to this packet")
    _validate_hashed_payload(key, "key_sha256", "adjudication key")

    packet_case_ids = [case["case_id"] for case in packet.get("cases") or []]
    if len(packet_case_ids) != len(set(packet_case_ids)):
        raise ValueError("packet contains duplicate case IDs")
    expected_ids = set(packet_case_ids)
    key_by_id = {case["case_id"]: case for case in key.get("cases") or []}
    if set(key_by_id) != expected_ids:
        raise ValueError("audit key case IDs do not match packet")

    submissions = [_load_submission(path) for path in review_paths]
    reviewer_ids = [submission.reviewer_id for submission in submissions]
    if len(reviewer_ids) != len(set(reviewer_ids)):
        raise ValueError("reviewer IDs must be unique")
    by_reviewer = {
        submission.reviewer_id: _validate_review_coverage(
            submission,
            packet_id=packet["packet_id"],
            packet_hash=packet_hash,
            expected_ids=expected_ids,
        )
        for submission in submissions
    }
    independent = [
        submission
        for submission in submissions
        if submission.reviewer_type in INDEPENDENT_REVIEWER_TYPES
    ]
    if len(independent) < 2:
        primary = independent
    else:
        primary = independent[:2]

    pairwise: list[dict[str, Any]] = []
    submission_by_id = {item.reviewer_id: item for item in submissions}
    for left_id, right_id in combinations(reviewer_ids, 2):
        left = by_reviewer[left_id]
        right = by_reviewer[right_id]
        left_decisions = [left[case_id].decision for case_id in packet_case_ids]
        right_decisions = [right[case_id].decision for case_id in packet_case_ids]
        decision_disagreements = [
            case_id
            for case_id in packet_case_ids
            if left[case_id].decision != right[case_id].decision
        ]
        taxonomy_disagreements = [
            case_id
            for case_id in packet_case_ids
            if set(left[case_id].error_types) != set(right[case_id].error_types)
        ]
        pairwise.append(
            {
                "reviewer_a": left_id,
                "reviewer_a_type": submission_by_id[left_id].reviewer_type,
                "reviewer_b": right_id,
                "reviewer_b_type": submission_by_id[right_id].reviewer_type,
                "case_count": len(packet_case_ids),
                "raw_agreement": _ratio(
                    len(packet_case_ids) - len(decision_disagreements),
                    len(packet_case_ids),
                ),
                "cohens_kappa": cohens_kappa(left_decisions, right_decisions),
                "decision_confusion": _decision_confusion(left, right, packet_case_ids),
                "decision_disagreement_count": len(decision_disagreements),
                "decision_disagreement_case_ids": decision_disagreements,
                "error_taxonomy_raw_agreement": _ratio(
                    len(packet_case_ids) - len(taxonomy_disagreements),
                    len(packet_case_ids),
                ),
                "error_taxonomy_disagreement_count": len(taxonomy_disagreements),
                "error_taxonomy_disagreement_case_ids": taxonomy_disagreements,
            }
        )

    primary_pair = None
    disagreement_packet = None
    adjudicator = None
    adjudicator_by_id = None
    if len(primary) >= 2:
        first, second = primary
        primary_pair = next(
            row
            for row in pairwise
            if {row["reviewer_a"], row["reviewer_b"]}
            == {first.reviewer_id, second.reviewer_id}
        )
        disagreement_packet = build_disagreement_packet(
            packet, primary_pair["decision_disagreement_case_ids"]
        )
        if adjudicator_path:
            adjudicator = _load_submission(adjudicator_path)
            if adjudicator.reviewer_type not in INDEPENDENT_REVIEWER_TYPES:
                raise ValueError("adjudicator must be human or independent_model")
            if adjudicator.reviewer_id in reviewer_ids:
                raise ValueError("adjudicator identity duplicates a primary reviewer")
            disagreement_ids = set(primary_pair["decision_disagreement_case_ids"])
            adjudicator_by_id = _validate_review_coverage(
                adjudicator,
                packet_id=disagreement_packet["packet_id"],
                packet_hash=disagreement_packet["packet_sha256"],
                expected_ids=disagreement_ids,
            )

    gold = None
    if len(primary) >= 2:
        gold = _build_gold(
            packet=packet,
            primary=primary,
            primary_by_id=by_reviewer,
            adjudicator=adjudicator,
            adjudicator_by_id=adjudicator_by_id,
        )
    summary = gold["summary"] if gold else {
        "decisive_count": 0,
        "accept_count": 0,
        "reject_count": 0,
        "ambiguous_count": len(packet_case_ids),
        "unresolved_disagreement_count": 0,
    }
    taxonomy = _taxonomy_gate(gold["cases"] if gold else [])
    independent_identities = {
        (
            item.reviewer_type,
            item.reviewer_id
            if item.reviewer_type == "human"
            else f"{item.model_family.casefold()}::{item.model_name.casefold()}",
        )
        for item in independent
    }
    independent_reviewers_distinct = len(independent_identities) >= 2
    agreement_value = primary_pair["raw_agreement"] if primary_pair else None
    kappa_value = primary_pair["cohens_kappa"] if primary_pair else None
    gate_checks = {
        "independent_reviewer_count": {
            "value": len(independent), "minimum": 2,
            "passed": len(independent) >= 2 and independent_reviewers_distinct,
        },
        "independently_reviewed_decisive": {
            "value": summary["decisive_count"], "minimum": 20,
            "passed": summary["decisive_count"] >= 20,
        },
        "gold_accepts": {
            "value": summary["accept_count"], "minimum": 8,
            "passed": summary["accept_count"] >= 8,
        },
        "gold_rejects": {
            "value": summary["reject_count"], "minimum": 8,
            "passed": summary["reject_count"] >= 8,
        },
        "raw_agreement": {
            "value": agreement_value, "minimum": 0.80,
            "passed": agreement_value is not None and agreement_value >= 0.80,
        },
        "cohens_kappa": {
            "value": kappa_value, "minimum": 0.60,
            "passed": kappa_value is not None and kappa_value >= 0.60,
        },
        "unresolved_ambiguous_rate": {
            "value": _ratio(summary["ambiguous_count"], len(packet_case_ids)),
            "maximum": 0.30,
            "passed": summary["ambiguous_count"] / len(packet_case_ids) <= 0.30,
        },
        "unresolved_disagreements": {
            "value": summary["unresolved_disagreement_count"], "maximum": 0,
            "passed": summary["unresolved_disagreement_count"] == 0,
        },
    }
    gate_passed = all(check["passed"] for check in gate_checks.values()) and all(
        check["passed"] for check in taxonomy.values()
    )
    all_submissions = [*submissions, *([adjudicator] if adjudicator else [])]
    report = {
        "schema_version": "state-guard-adjudication-report-v2",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet_hash,
        "case_count": len(packet_case_ids),
        "reviewer_count": len(submissions),
        "independent_reviewer_count": len(independent),
        "reviewers": [_reviewer_summary(item) for item in all_submissions],
        "pairwise_agreement": pairwise,
        "primary_pair": primary_pair,
        "confidence_distribution": _confidence_distribution(submissions),
        "disagreement_packet": {
            "packet_id": disagreement_packet["packet_id"] if disagreement_packet else None,
            "packet_sha256": disagreement_packet["packet_sha256"] if disagreement_packet else None,
            "case_count": disagreement_packet["case_count"] if disagreement_packet else 0,
        },
        "gold_summary": summary,
        "taxonomy_gate": taxonomy,
        "review_gate": {
            "checks": gate_checks,
            "passed": gate_passed,
            "decision": "PASS_INDEPENDENT_REVIEW_GATE" if gate_passed else "BLOCK_REAL_REPLAY",
            "behavior_change_allowed": False,
            "reason": (
                "Independent review Gate passed; real reviewed evidence is still required."
                if gate_passed
                else "One or more independent review, agreement, ambiguity, or taxonomy requirements failed."
            ),
        },
        "ground_truth_status": (
            "independent_review_gold_frozen" if gate_passed else "incomplete_or_provisional"
        ),
        "cost": {
            "provider_calls": sum(item.usage.provider_calls for item in all_submissions),
            "input_tokens": sum(item.usage.input_tokens for item in all_submissions),
            "output_tokens": sum(item.usage.output_tokens for item in all_submissions),
            "total_tokens": sum(item.usage.total_tokens for item in all_submissions),
        },
        "gold_labels_sha256": gold.get("gold_sha256") if gold else None,
    }
    report["report_sha256"] = _stable_hash(report)
    report["_disagreement_packet_payload"] = disagreement_packet
    report["_gold_payload"] = gold
    return report


def render_markdown(report: dict[str, Any]) -> str:
    pair = report.get("primary_pair") or {}
    summary = report["gold_summary"]
    lines = [
        "# StateGuard independent adjudication report",
        "",
        f"- Packet: `{report['packet_id']}`",
        f"- Cases: {report['case_count']}",
        f"- Independent reviewers: {report['independent_reviewer_count']}",
        f"- Raw agreement: {pair.get('raw_agreement', '—')}",
        f"- Cohen's kappa: {pair.get('cohens_kappa', '—')}",
        f"- Decision disagreements: {pair.get('decision_disagreement_count', '—')}",
        f"- Gold decisive accepts/rejects: {summary['accept_count']} / {summary['reject_count']}",
        f"- Gold ambiguous: {summary['ambiguous_count']}",
        f"- Unresolved disagreements: {summary['unresolved_disagreement_count']}",
        "",
        "## Reviewers",
        "",
        "| Reviewer | Type | Model family | Model | Decisive | Mean confidence | Tokens |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for reviewer in report["reviewers"]:
        lines.append(
            f"| {reviewer['reviewer_id']} | {reviewer['reviewer_type']} | "
            f"{reviewer['model_family'] or '—'} | {reviewer['model_name'] or '—'} | "
            f"{reviewer['decisive_count']} | {reviewer['mean_confidence']} | "
            f"{reviewer['usage']['total_tokens']} |"
        )
    lines.extend(
        [
            "",
            "## Gate",
            "",
            f"Decision: `{report['review_gate']['decision']}`",
            "",
        ]
    )
    for name, check in report["review_gate"]["checks"].items():
        lines.append(f"- {name}: {check['value']} — {'PASS' if check['passed'] else 'FAIL'}")
    for name, check in report["taxonomy_gate"].items():
        lines.append(f"- taxonomy {name}: {check['value']} — {'PASS' if check['passed'] else 'FAIL'}")
    lines.extend(
        [
            "",
            "Independent-model labels are not human ground truth. Production behavior "
            "remains unchanged even when this review Gate passes.",
            "",
            f"Report SHA-256: `{report['report_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write_text(path: Path, text: str) -> None:
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
    parser.add_argument("packet", help="blind adjudication packet JSON")
    parser.add_argument("key", help="withheld audit key JSON")
    parser.add_argument("reviews", nargs="+", help="completed primary review JSON")
    parser.add_argument("--adjudicator-review")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--out-disagreement-packet")
    parser.add_argument("--out-gold")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_adjudication_report(
        Path(args.packet).resolve(),
        Path(args.key).resolve(),
        [Path(value).resolve() for value in args.reviews],
        adjudicator_path=(
            Path(args.adjudicator_review).resolve() if args.adjudicator_review else None
        ),
    )
    disagreement = report.pop("_disagreement_packet_payload")
    gold = report.pop("_gold_payload")
    # Re-hash after removing internal write payloads.
    report.pop("report_sha256", None)
    report["report_sha256"] = _stable_hash(report)
    _atomic_write_text(
        Path(args.out_json).resolve(),
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write_text(Path(args.out_md).resolve(), render_markdown(report))
    if args.out_disagreement_packet and disagreement is not None:
        _atomic_write_text(
            Path(args.out_disagreement_packet).resolve(),
            json.dumps(disagreement, ensure_ascii=False, indent=2) + "\n",
        )
    if args.out_gold and gold is not None:
        _atomic_write_text(
            Path(args.out_gold).resolve(),
            json.dumps(gold, ensure_ascii=False, indent=2) + "\n",
        )
    print(
        json.dumps(
            {
                "reviewer_count": report["reviewer_count"],
                "independent_reviewer_count": report["independent_reviewer_count"],
                "raw_agreement": (report.get("primary_pair") or {}).get("raw_agreement"),
                "cohens_kappa": (report.get("primary_pair") or {}).get("cohens_kappa"),
                "gold_decisive": report["gold_summary"]["decisive_count"],
                "review_gate": report["review_gate"]["decision"],
                "behavior_change_allowed": False,
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["review_gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
