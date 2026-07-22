"""Compare two or more author long-range analysis or report JSON files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.analyze_author_longrange import analyze
except ModuleNotFoundError:  # Direct ``python scripts/compare_author_longrange.py``.
    from analyze_author_longrange import analyze


FIELDS = (
    "sections",
    "contract_pass_rate",
    "repair_rate",
    "repair_success_rate",
    "hard_rejects",
    "state_conflicts",
    "max_active_threads",
    "final_memory_records",
    "mean_consecutive_ngram_overlap",
    "total_tokens",
    "mean_latency_seconds",
    "provider_errors",
    "runtime_rebuilds",
)


def _as_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    return payload if "metrics" in payload and "gate" in payload else analyze(payload)


def render_comparison(analyses: list[dict[str, Any]]) -> str:
    headers = [str(item.get("run_id", "unknown")) for item in analyses]
    lines = [
        "# Author Long-Run Comparison",
        "",
        "| Metric | " + " | ".join(headers) + " |",
        "| --- | " + " | ".join("---:" for _ in headers) + " |",
        "| gate | " + " | ".join(str(item.get("gate")) for item in analyses) + " |",
    ]
    for field in FIELDS:
        values = [str(item.get("metrics", {}).get(field, "n/a")) for item in analyses]
        lines.append(f"| {field} | " + " | ".join(values) + " |")
    lines.extend(
        [
            "",
            "Evidence boundaries remain run-specific; this comparison does not promote "
            "recorded evidence to real-provider or human-review evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()
    if len(args.inputs) < 2:
        parser.error("at least two reports or analyses are required")
    analyses = [
        _as_analysis(json.loads(path.read_text(encoding="utf-8")))
        for path in args.inputs
    ]
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text(render_comparison(analyses), encoding="utf-8")
    print(str(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
