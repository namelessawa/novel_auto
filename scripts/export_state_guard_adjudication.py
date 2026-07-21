"""Export a label-blind StateGuard adjudication packet and a separate audit key.

The reviewer packet deliberately excludes production decisions, verifier verdicts,
fixture labels and source filenames.  The audit key is written separately and must
not be given to reviewers before their decisions are frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


PACKET_SCHEMA_VERSION = "state-guard-adjudication-packet-v1"
KEY_SCHEMA_VERSION = "state-guard-adjudication-key-v1"
QUESTIONS = [
    "正文是否完成所有必达终态？",
    "正文是否改变了无来源事实？",
    "ledger 是否准确表达正文结尾？",
    "应当接受、拒绝还是无法判断？",
]


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}_", suffix=".tmp", dir=str(path.parent)
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


def _extract_cases(report: dict[str, Any], source_index: int) -> list[dict[str, Any]]:
    extracted: list[dict[str, Any]] = []
    for case_index, case in enumerate(report.get("cases") or []):
        ticks = case.get("ticks") or []
        if not ticks or not isinstance(ticks[-1].get("guard_trace"), dict):
            raise ValueError(
                f"source {source_index} case {case_index} has no complete Guard trace"
            )
        trace = ticks[-1]["guard_trace"]
        missing = (trace.get("payload_completeness") or {}).get("missing_fields")
        if missing:
            raise ValueError(
                f"source {source_index} case {case_index} has payload loss: {missing}"
            )
        fixture_id = str(case.get("fixture_id") or trace.get("fixture_id") or "")
        if not fixture_id:
            raise ValueError(f"source {source_index} case {case_index} lacks fixture_id")
        expected = (case.get("expectations") or {}).get("expected_acceptance")
        if expected not in {"accept", "reject", "ambiguous"}:
            raise ValueError(
                f"source {source_index} case {fixture_id} lacks an expected decision"
            )
        blind_payload = {
            "previous_state": (
                trace.get("previous_typed_state")
                or trace.get("previous_legacy_state")
                or {}
            ),
            "required_end_states": trace.get("required_end_states") or [],
            "prose": trace.get("original_draft") or "",
            "declared_typed_state": (
                trace.get("original_declared_typed_state") or {}
            ),
            # The captured runtime currently supplies relevant location nodes, not
            # an ontology edge list.  Preserve that limitation instead of inventing
            # topology for the reviewer.
            "location_relations": trace.get("location_context") or [],
            "knowledge_boundaries": trace.get("knowledge_boundaries") or [],
            "questions": list(QUESTIONS),
        }
        if not blind_payload["prose"]:
            raise ValueError(f"source {source_index} case {fixture_id} lacks prose")
        extracted.append(
            {
                "fixture_id": fixture_id,
                "expected_final_decision": expected,
                "expected_error_types": list(case.get("expected_error_types") or []),
                "recorded_final_decision": trace.get("final_decision"),
                "source_index": source_index,
                "source_case_index": case_index,
                "trace_id": trace.get("trace_id"),
                "trace_schema_version": trace.get("schema_version"),
                "blind_payload": blind_payload,
                "blind_hash": _stable_hash(blind_payload),
            }
        )
    return extracted


def build_adjudication_exports(
    source_paths: list[Path],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return reviewer packet, withheld audit key and blank review template."""

    if not source_paths:
        raise ValueError("at least one replay report is required")
    extracted: list[dict[str, Any]] = []
    source_audit: list[dict[str, Any]] = []
    for index, source_path in enumerate(source_paths, start=1):
        raw = source_path.read_bytes()
        report = json.loads(raw.decode("utf-8"))
        source_audit.append(
            {
                "source_index": index,
                "source_filename": source_path.name,
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "source_schema_version": report.get("schema_version"),
                "source_suite_id": report.get("suite_id"),
            }
        )
        extracted.extend(_extract_cases(report, index))

    fixture_ids = [row["fixture_id"] for row in extracted]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("fixture IDs must be unique across replay reports")

    # Content-hash order prevents source ordering from exposing negative/positive
    # suite membership.  Opaque IDs contain no fixture name or experiment label.
    extracted.sort(key=lambda row: row["blind_hash"])
    packet_cases: list[dict[str, Any]] = []
    key_cases: list[dict[str, Any]] = []
    template_results: list[dict[str, Any]] = []
    for ordinal, row in enumerate(extracted, start=1):
        opaque_id = f"sg-{ordinal:03d}-{row['blind_hash'][:8]}"
        packet_cases.append({"case_id": opaque_id, **row["blind_payload"]})
        key_cases.append(
            {
                "case_id": opaque_id,
                "fixture_id": row["fixture_id"],
                "expected_final_decision": row["expected_final_decision"],
                "expected_error_types": row["expected_error_types"],
                "recorded_final_decision": row["recorded_final_decision"],
                "source_index": row["source_index"],
                "source_case_index": row["source_case_index"],
                "trace_id": row["trace_id"],
                "trace_schema_version": row["trace_schema_version"],
                "blind_payload_sha256": row["blind_hash"],
            }
        )
        template_results.append(
            {
                "case_id": opaque_id,
                "decision": "ambiguous",
                "error_types": [],
                "confidence": 0.0,
                "rationale": "",
            }
        )

    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": "phase9-state-guard-blind-v1",
        "reviewer_instructions": (
            "请仅依据提供的前态、必达终态、正文、声明 ledger、地点和知识边界"
            "独立裁决；不要索取运行时决定、verifier 结论或隐藏标签。"
        ),
        "case_count": len(packet_cases),
        "cases": packet_cases,
    }
    packet["packet_sha256"] = _stable_hash(packet)
    key = {
        "schema_version": KEY_SCHEMA_VERSION,
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "withheld_from_reviewers": True,
        "warning": "Freeze reviewer decisions before opening this audit key.",
        "source_audit": source_audit,
        "cases": key_cases,
    }
    key["key_sha256"] = _stable_hash(key)
    template = {
        "schema_version": "state-guard-adjudication-review-v1",
        "packet_id": packet["packet_id"],
        "packet_sha256": packet["packet_sha256"],
        "reviewer_id": "replace-with-opaque-reviewer-id",
        "reviewer_type": "project_agent",
        "results": template_results,
    }
    return packet, key, template


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", help="complete Guard replay report JSON")
    parser.add_argument("--out-packet", required=True, help="label-blind reviewer JSON")
    parser.add_argument("--out-key", required=True, help="withheld audit key JSON")
    parser.add_argument("--out-template", required=True, help="blank review JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    packet, key, template = build_adjudication_exports(
        [Path(value).resolve() for value in args.reports]
    )
    _atomic_write(Path(args.out_packet).resolve(), packet)
    _atomic_write(Path(args.out_key).resolve(), key)
    _atomic_write(Path(args.out_template).resolve(), template)
    print(
        json.dumps(
            {
                "packet_id": packet["packet_id"],
                "case_count": packet["case_count"],
                "packet_sha256": packet["packet_sha256"],
                "labels_exposed_in_packet": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
