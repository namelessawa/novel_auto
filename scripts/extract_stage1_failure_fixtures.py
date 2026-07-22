"""Extract sanitized Stage 1 rejected transactions into a frozen replay fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / ".tmp" / "narrative-contract-stage1-20260722-final" / "runs"
DEFAULT_OUTPUT = ROOT / "backend" / "tests" / "fixtures" / "stage1_event_repair_failures.json"


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(prefix=path.name + ".", suffix=".partial", dir=path.parent)
    partial = Path(raw)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(partial, path)
    finally:
        if partial.exists():
            partial.unlink()


def _fixed_repair_text(contract: dict[str, Any]) -> str:
    parts = [
        "暴雨后的旧灯塔仍带着潮湿盐味。沈砚与林秋只核对已经确认的旧信记录，没有增加新的责任人、日期或关系。"
    ]
    for event in contract.get("required_events", []):
        action = str(event.get("action") or "")
        match = re.search(r"第(\d+)处", action)
        if "交给林秋" in action:
            parts.append("沈砚把旧信交给林秋，林秋接过旧信并收好。")
        elif match:
            index = match.group(1)
            parts.append(
                f"林秋核对旧信第{index}处记录并继续保管，把信封收好后放进抽屉。"
            )
        else:
            actor = str(event.get("actor") or "指定人物")
            target = str(event.get("target") or "指定对象")
            parts.append(f"{actor}对{target}实际完成了“{action}”，该动作已经结束。")
    for state in contract.get("required_end_state", []):
        path = str(state.get("path") or "")
        expected = str(state.get("expected") or "")
        if path.endswith("/holder") and expected in {"lin_qiu", "林秋"}:
            parts.append("本节结束时，林秋持有旧信；她把旧信收进抽屉继续保管。")
        elif path.endswith("/holder"):
            parts.append(f"本节结束时，{expected}已经接收并持有该物品。")
        else:
            parts.append(f"本节结束时，{path} 已明确达到 {expected}。")
    text = "".join(parts)
    length = contract.get("length_constraint", {})
    minimum = int(length.get("min_chars", 1))
    maximum = int(length.get("max_chars", max(minimum, 3000)))
    padding = "灯光扫过桌面，两人继续核对既有事实，并确认刚才的动作已经完成。"
    while sum(not char.isspace() for char in text) < minimum:
        text += padding
    if sum(not char.isspace() for char in text) > maximum:
        raise ValueError("fixed replay text exceeds contract maximum")
    return text


def extract(input_root: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for transaction_path in sorted(
        input_root.glob("*/runtime/generation_transactions/*.json")
    ):
        if transaction_path.name.endswith(".bak"):
            continue
        transaction = json.loads(transaction_path.read_text(encoding="utf-8"))
        if transaction.get("phase") != "rejected":
            continue
        combo = transaction_path.parents[2].name
        theme, style = combo.split("__", 1)
        history = transaction.get("candidate_history") or []
        if len(history) < 2:
            raise ValueError(f"rejected transaction lacks repair history: {combo}")
        contract = transaction["narrative_contract"]
        attempt_match = re.search(r"(\d+)$", str(transaction["id"]))
        attempt = int(attempt_match.group(1)) if attempt_match else len(cases) + 1
        narrative_history = transaction.get("narrative_validation_history") or []
        state_history = transaction.get("validation_history") or []
        final_codes = [
            item["code"]
            for report in (narrative_history[-1:] + state_history[-1:])
            for item in report.get("violations", [])
        ]
        original = history[0]
        cases.append(
            {
                "case_id": f"{theme}__{style}__attempt_{attempt:02d}",
                "theme": theme,
                "style": style,
                "section_goal": {
                    "section_id": transaction["section_id"],
                    "objective": "；".join(
                        str(item.get("description") or item.get("action") or "")
                        for item in contract.get("required_events", [])
                    ),
                    "desired_length": int(
                        contract.get("length_constraint", {}).get("max_chars", 800)
                    )
                    // 2,
                },
                "narrative_contract": contract,
                "original_candidate": original,
                "original_sha256": hashlib.sha256(
                    original["narrative_text"].encode("utf-8")
                ).hexdigest(),
                "first_validation": {
                    "narrative": narrative_history[0],
                    "authority": state_history[0],
                },
                "repair_output": {"narrative_text": history[-1]["narrative_text"]},
                "fixed_repair_output": {
                    "narrative_text": _fixed_repair_text(contract)
                },
                "final_validation": {
                    "narrative": narrative_history[-1],
                    "authority": state_history[-1],
                },
                "expected_failure_codes": list(dict.fromkeys(final_codes)),
            }
        )
    if len(cases) != 24:
        raise ValueError(f"expected 24 rejected Stage 1 cases, found {len(cases)}")
    return {
        "schema_version": 1,
        "source": "stage1_real_matrix_20260722_sanitized",
        "evidence_boundary": "recorded real-provider outputs; fixed repair responses are deterministic replay data",
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
