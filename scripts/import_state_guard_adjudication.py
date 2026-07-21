"""Validate blind StateGuard reviews and report reviewer agreement.

Human, independent-model and project-agent reviews remain separate.  Only human
reviews count toward the Phase 9 independent-review behavior gate; model-assisted
or project-agent results are always provisional.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from itertools import combinations
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


DECISIONS = ("accept", "reject", "ambiguous")


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    decision: str
    error_types: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        if value not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}")
        return value


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^state-guard-adjudication-review-v1$")
    packet_id: str
    packet_sha256: str
    reviewer_id: str = Field(min_length=3, max_length=100)
    reviewer_type: str
    results: list[ReviewResult]

    @field_validator("reviewer_type")
    @classmethod
    def validate_reviewer_type(cls, value: str) -> str:
        allowed = {"human", "independent_model", "project_agent"}
        if value not in allowed:
            raise ValueError(f"reviewer_type must be one of {sorted(allowed)}")
        return value


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


def _load_submission(path: Path) -> ReviewSubmission:
    return ReviewSubmission.model_validate_json(path.read_text(encoding="utf-8"))


def build_adjudication_report(
    packet_path: Path,
    key_path: Path,
    review_paths: list[Path],
) -> dict[str, Any]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    if packet.get("schema_version") != "state-guard-adjudication-packet-v1":
        raise ValueError("unsupported adjudication packet schema")
    packet_without_hash = dict(packet)
    stored_packet_hash = packet_without_hash.pop("packet_sha256", None)
    if stored_packet_hash != _stable_hash(packet_without_hash):
        raise ValueError("adjudication packet hash mismatch")
    if key.get("packet_sha256") != stored_packet_hash:
        raise ValueError("audit key is not bound to this packet")
    key_without_hash = dict(key)
    stored_key_hash = key_without_hash.pop("key_sha256", None)
    if stored_key_hash != _stable_hash(key_without_hash):
        raise ValueError("adjudication key hash mismatch")

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
    by_reviewer: dict[str, dict[str, ReviewResult]] = {}
    reviewer_summary: list[dict[str, Any]] = []
    for submission in submissions:
        if submission.packet_id != packet["packet_id"]:
            raise ValueError(f"review {submission.reviewer_id} packet_id mismatch")
        if submission.packet_sha256 != stored_packet_hash:
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
        indexed = {item.case_id: item for item in submission.results}
        by_reviewer[submission.reviewer_id] = indexed
        decisive = sum(item.decision != "ambiguous" for item in submission.results)
        reviewer_summary.append(
            {
                "reviewer_id": submission.reviewer_id,
                "reviewer_type": submission.reviewer_type,
                "case_count": len(submission.results),
                "decisive_count": decisive,
                "mean_confidence": round(
                    sum(item.confidence for item in submission.results)
                    / len(submission.results),
                    6,
                ) if submission.results else None,
                "provisional": submission.reviewer_type != "human",
            }
        )

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
        agreements = len(packet_case_ids) - len(decision_disagreements)
        pairwise.append(
            {
                "reviewer_a": left_id,
                "reviewer_a_type": submission_by_id[left_id].reviewer_type,
                "reviewer_b": right_id,
                "reviewer_b_type": submission_by_id[right_id].reviewer_type,
                "case_count": len(packet_case_ids),
                "raw_agreement": _ratio(agreements, len(packet_case_ids)),
                "cohens_kappa": cohens_kappa(left_decisions, right_decisions),
                "decision_disagreement_count": len(decision_disagreements),
                "decision_disagreement_case_ids": decision_disagreements,
                "error_taxonomy_disagreement_count": len(taxonomy_disagreements),
                "error_taxonomy_disagreement_case_ids": taxonomy_disagreements,
            }
        )

    # A decisive case counts toward the behavior gate only when at least one actual
    # human supplied a decisive review.  Model and project-agent reviews remain
    # useful diagnostics but cannot unlock production behavior.
    human_ids = [
        item.reviewer_id for item in submissions if item.reviewer_type == "human"
    ]
    independently_reviewed_decisive = sum(
        any(by_reviewer[reviewer_id][case_id].decision != "ambiguous" for reviewer_id in human_ids)
        for case_id in packet_case_ids
    )
    model_reviewed_decisive = sum(
        any(
            by_reviewer[item.reviewer_id][case_id].decision != "ambiguous"
            for item in submissions
            if item.reviewer_type in {"independent_model", "project_agent"}
        )
        for case_id in packet_case_ids
    )
    report = {
        "schema_version": "state-guard-adjudication-report-v1",
        "packet_id": packet["packet_id"],
        "packet_sha256": stored_packet_hash,
        "case_count": len(packet_case_ids),
        "reviewer_count": len(submissions),
        "reviewers": reviewer_summary,
        "pairwise_agreement": pairwise,
        "independently_human_reviewed_decisive_cases": independently_reviewed_decisive,
        "model_or_project_reviewed_decisive_cases": model_reviewed_decisive,
        "behavior_gate": {
            "minimum_independent_human_decisive_cases": 20,
            "independent_review_gate_passed": independently_reviewed_decisive >= 20,
            "behavior_change_allowed": False,
            "reason": (
                "Independent human review threshold is not met."
                if independently_reviewed_decisive < 20
                else "Other Phase 9 behavior gates must still be evaluated."
            ),
        },
        "ground_truth_status": (
            "human_review_available" if human_ids else "provisional_or_unreviewed"
        ),
    }
    report["report_sha256"] = _stable_hash(report)
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# StateGuard blind adjudication report",
        "",
        f"- Packet: `{report['packet_id']}`",
        f"- Cases: {report['case_count']}",
        f"- Reviewers: {report['reviewer_count']}",
        "- Independent human-reviewed decisive cases: "
        f"{report['independently_human_reviewed_decisive_cases']}",
        f"- Ground-truth status: `{report['ground_truth_status']}`",
        "",
        "## Pairwise agreement",
        "",
    ]
    if not report["pairwise_agreement"]:
        lines.append("No reviewer pair is available; agreement is undefined.")
    else:
        lines.extend(
            [
                "| Reviewers | Raw agreement | Cohen's kappa | Decision disagreement | Taxonomy disagreement |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in report["pairwise_agreement"]:
            kappa = "—" if row["cohens_kappa"] is None else f"{row['cohens_kappa']:.3f}"
            lines.append(
                f"| {row['reviewer_a']} / {row['reviewer_b']} | "
                f"{row['raw_agreement']:.3f} | {kappa} | "
                f"{row['decision_disagreement_count']} | "
                f"{row['error_taxonomy_disagreement_count']} |"
            )
    lines.extend(
        [
            "",
            "## Behavior gate",
            "",
            f"- Passed: {report['behavior_gate']['independent_review_gate_passed']}",
            f"- Behavior change allowed: {report['behavior_gate']['behavior_change_allowed']}",
            f"- Reason: {report['behavior_gate']['reason']}",
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
    parser.add_argument("reviews", nargs="+", help="one or more completed review JSON")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_adjudication_report(
        Path(args.packet).resolve(),
        Path(args.key).resolve(),
        [Path(value).resolve() for value in args.reviews],
    )
    _atomic_write_text(
        Path(args.out_json).resolve(),
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write_text(Path(args.out_md).resolve(), render_markdown(report))
    print(
        json.dumps(
            {
                "reviewer_count": report["reviewer_count"],
                "independent_human_decisive": report[
                    "independently_human_reviewed_decisive_cases"
                ],
                "behavior_change_allowed": report["behavior_gate"][
                    "behavior_change_allowed"
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
