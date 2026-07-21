"""Convert Phase 7 StateGuard traces into loss-aware recorded replay cases.

The source artifacts do not retain rejected Narrator drafts or complete repair
prose.  This converter deliberately preserves that absence instead of synthesizing
text.  It replays only the final decision that can be derived from the recorded
guard trace and narrative persistence result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal


Decision = Literal["accept", "reject"]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def replay_recorded_decision(trace: dict[str, Any]) -> Decision:
    """Derive the production decision without interpreting prose correctness."""
    if bool(trace.get("adopted")) or bool(trace.get("repair_retry_adopted")):
        return "accept"
    before = trace.get("before") or {}
    if not bool(trace.get("repair_attempted")) and bool(before.get("safe")):
        return "accept"
    return "reject"


def _evidence_excerpts(trace: dict[str, Any], limit: int = 8) -> list[str]:
    excerpts: list[str] = []
    for stage_name in ("before", "after", "after_retry"):
        stage = trace.get(stage_name) or {}
        for check in stage.get("event_checks") or []:
            for excerpt in check.get("prose_evidence") or []:
                text = str(excerpt).strip()
                if text and text not in excerpts:
                    excerpts.append(text)
                    if len(excerpts) >= limit:
                        return excerpts
        for conflict in stage.get("ledger_conflicts") or []:
            if not isinstance(conflict, dict):
                continue
            for excerpt in conflict.get("prose_evidence") or []:
                text = str(excerpt).strip()
                if text and text not in excerpts:
                    excerpts.append(text)
                    if len(excerpts) >= limit:
                        return excerpts
    return excerpts


def _source_descriptor(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") or {}
    provider = metadata.get("provider") or {}
    return {
        "filename": path.name,
        "sha256": _sha256_bytes(path.read_bytes()),
        "git_sha": str(metadata.get("git_sha") or ""),
        "provider": str(provider.get("provider") or ""),
        "model": str(provider.get("model") or ""),
        "mode": str(metadata.get("mode") or ""),
        "result_count": len(payload.get("results") or []),
    }


def convert_sources(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        raise ValueError("at least one Phase 7 artifact is required")

    sources: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted((item.resolve() for item in paths), key=lambda item: item.name):
        payload = json.loads(path.read_text(encoding="utf-8"))
        descriptor = _source_descriptor(path, payload)
        sources.append(descriptor)
        for result_index, result in enumerate(payload.get("results") or []):
            for tick_output in result.get("tick_outputs") or []:
                trace = tick_output.get("continuity_guard_trace") or {}
                tick = int(tick_output.get("tick") or 0)
                style = str(result.get("style") or "")
                case_id = f"{path.stem}:{result_index:02d}:{style}:tick-{tick:03d}"
                if case_id in seen:
                    raise ValueError(f"duplicate replay case id: {case_id}")
                seen.add(case_id)

                decision = replay_recorded_decision(trace)
                text = str(tick_output.get("text") or "")
                persisted_decision: Decision = "accept" if text else "reject"
                case = {
                    "case_id": case_id,
                    "source": {
                        "filename": path.name,
                        "sha256": descriptor["sha256"],
                        "result_index": result_index,
                    },
                    "scenario": str(result.get("scenario") or ""),
                    "theme": str(result.get("theme") or ""),
                    "style": style,
                    "tick": tick,
                    "required_events": trace.get("required_events") or [],
                    "known_entities": trace.get("known_entities") or [],
                    "entity_names": trace.get("entity_names") or {},
                    "tracking_character_id": str(
                        trace.get("tracking_character_id") or ""
                    ),
                    "before": trace.get("before") or {},
                    "repair_declared": trace.get("repair_declared") or [],
                    "repair_guard": trace.get("repair_guard") or {},
                    "after": trace.get("after") or {},
                    "repair_retry_declared": (
                        trace.get("repair_retry_declared") or []
                    ),
                    "repair_retry_guard": trace.get("repair_retry_guard") or {},
                    "after_retry": trace.get("after_retry") or {},
                    "reject_reason": str(trace.get("reject_reason") or ""),
                    "recorded_final_decision": decision,
                    "persisted_output_decision": persisted_decision,
                    "decision_replay_matches_persistence": (
                        decision == persisted_decision
                    ),
                    "accepted_text_sha256": (
                        _sha256_bytes(text.encode("utf-8")) if text else ""
                    ),
                    "accepted_text_char_count": len(text),
                    "evidence_excerpts": _evidence_excerpts(trace),
                    "completeness": {
                        "accepted_text_available_in_source": bool(text),
                        "accepted_text_copied_to_conversion": False,
                        "rejected_draft_available": False,
                        "full_repair_text_available": False,
                        "verifier_payloads_available": bool(trace.get("before")),
                        "decision_trace_available": bool(trace),
                    },
                    "review_status": "unreviewed",
                    "human_labels": [],
                    "adjudicated_label": None,
                    "error_types": [],
                }
                cases.append(case)

    cases.sort(key=lambda item: item["case_id"])
    decisions = {"accept": 0, "reject": 0}
    for case in cases:
        decisions[case["recorded_final_decision"]] += 1
    summary = {
        "source_count": len(sources),
        "case_count": len(cases),
        "decision_counts": decisions,
        "reproduced_decision_count": sum(
            bool(case["decision_replay_matches_persistence"]) for case in cases
        ),
        "accepted_text_available_count": sum(
            bool(case["completeness"]["accepted_text_available_in_source"])
            for case in cases
        ),
        "rejected_draft_available_count": sum(
            bool(case["completeness"]["rejected_draft_available"])
            for case in cases
        ),
        "full_repair_text_available_count": sum(
            bool(case["completeness"]["full_repair_text_available"])
            for case in cases
        ),
        "unreviewed_count": len(cases),
    }
    result = {
        "schema_version": "phase7-guard-recorded-v1",
        "provenance": {
            "kind": "sanitized_recorded_guard_trace",
            "scope": "decision_and_evidence_replay_only",
            "limitations": [
                "Rejected Narrator drafts were not retained by the source artifacts.",
                "Repair declarations and verifier outputs exist, but full repair prose was not retained.",
                "Recorded decisions are production outcomes, not human ground truth.",
            ],
        },
        "source_artifacts": sources,
        "summary": summary,
        "cases": cases,
    }
    result["cases_sha256"] = _stable_sha256(cases)
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
    parser.add_argument("inputs", nargs="+", help="Phase 7 validate JSON artifacts")
    parser.add_argument("--out", required=True, help="Converted replay JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = convert_sources([Path(item) for item in args.inputs])
    write_json(Path(args.out).resolve(), result)
    print(
        json.dumps(
            {
                "out": str(Path(args.out).resolve()),
                "cases": result["summary"]["case_count"],
                "reproduced": result["summary"]["reproduced_decision_count"],
                "cases_sha256": result["cases_sha256"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
