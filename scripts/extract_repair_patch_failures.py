"""Freeze the final six real Stage 1 rejects for offline Patch replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    ROOT
    / ".tmp"
    / "event-completion-repair"
    / "mini-matrix-r4-20260722"
    / "runs"
)
DEFAULT_OUTPUT = (
    ROOT
    / "backend"
    / "tests"
    / "fixtures"
    / "repair_patch_real_failures.json"
)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".partial",
        dir=path.parent,
    )
    partial = Path(raw)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(partial, path)
    finally:
        if partial.exists():
            partial.unlink()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract(input_root: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    paths = sorted(input_root.glob("*/runtime/generation_transactions/*.json"))
    for path in paths:
        if path.name.endswith(".bak"):
            continue
        transaction = json.loads(path.read_text(encoding="utf-8"))
        if transaction.get("phase") != "rejected":
            continue
        history = transaction.get("candidate_history") or []
        if len(history) != 2:
            raise ValueError(f"expected two Writer attempts: {path}")
        combo = path.parents[2].name
        theme, style = combo.split("__", 1)
        contract = transaction["narrative_contract"]
        required_events = contract.get("required_events") or []
        objective = "；".join(
            str(item.get("description") or item.get("action") or "")
            for item in required_events
        )
        maximum = int(
            contract.get("length_constraint", {}).get("max_chars", 800)
        )
        initial_reports = transaction.get("narrative_validation_history") or []
        state_reports = transaction.get("validation_history") or []
        if len(initial_reports) != 2 or len(state_reports) != 2:
            raise ValueError(f"missing before/after validator evidence: {path}")
        original = history[0]
        provider_repair = history[1]
        cases.append(
            {
                "case_id": f"{combo}__{path.stem}",
                "theme": theme,
                "style": style,
                "section_goal": {
                    "section_id": transaction["section_id"],
                    "objective": objective,
                    "desired_length": max(1, maximum // 2),
                },
                "narrative_contract": contract,
                "event_execution_plan": transaction["event_execution_plan"],
                "original_candidate": original,
                "original_sha256": _sha256(original["narrative_text"]),
                "provider_repair_output": provider_repair,
                "provider_repair_sha256": _sha256(
                    provider_repair["narrative_text"]
                ),
                "recorded_validation": {
                    "initial_narrative": initial_reports[0],
                    "initial_authority": state_reports[0],
                    "provider_repair_narrative": initial_reports[1],
                    "provider_repair_authority": state_reports[1],
                },
                "recorded_usage": {
                    key: int(value)
                    for key, value in transaction.get("usage", {}).items()
                    if isinstance(value, int)
                },
            }
        )
    if len(cases) != 6:
        raise ValueError(f"expected final six real rejects, found {len(cases)}")
    return {
        "schema_version": 1,
        "source": "stage1_real_15_glm52_r4_20260722_sanitized",
        "evidence_boundary": (
            "recorded real-provider original and failed Repair outputs; "
            "correct patches are derived and validated offline"
        ),
        "case_count": len(cases),
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = extract(args.input_root.resolve())
    _atomic_json(args.output.resolve(), payload)
    print(
        json.dumps(
            {"cases": payload["case_count"], "output": args.output.name},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
