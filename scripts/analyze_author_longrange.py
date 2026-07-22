"""Analyze an author long-range report without invoking an LLM provider."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def analyze(report: dict[str, Any]) -> dict[str, Any]:
    sections = report.get("sections", [])
    summary = report.get("summary", {})
    accepted = [item for item in sections if item.get("narrative_contract_pass")]
    repaired = [item for item in sections if item.get("repair_performed")]
    repaired_and_accepted = [
        item for item in repaired if item.get("narrative_contract_pass")
    ]
    samples = report.get("real_sample_replay", {})
    recovery = report.get("recovery_evidence", {})
    stage0_checks = {
        "sections_attempted": bool(sections),
        "all_attempted_committed": bool(sections)
        and all(item.get("committed") for item in sections),
        "all_final_contracts_accepted": bool(sections)
        and len(accepted) == len(sections),
        "no_hard_rejects": int(summary.get("hard_rejects", 0)) == 0,
        "no_failures": not report.get("failures"),
        "all_five_real_samples_rejected": len(samples) == 5
        and all(not item.get("accepted") for item in samples.values()),
        "section_ids_unique": recovery.get("section_ids_unique") is True,
        "canonical_revision_contiguous": recovery.get(
            "canonical_revision_contiguous"
        )
        is True,
        "clean_staged_recovery": recovery.get("clean_staged_recovery", {}).get(
            "passed"
        )
        is True,
        "stale_staged_rejected": recovery.get("stale_staged_rejected", {}).get(
            "passed"
        )
        is True,
    }
    mode = report.get("config", {}).get("mode")
    stage0_pass = mode == "recorded" and all(stage0_checks.values())
    violations = Counter(
        code
        for sample in samples.values()
        for code in sample.get("codes", [])
    )
    analysis = {
        "schema_version": 1,
        "run_id": report.get("run_id"),
        "source_stage": report.get("stage"),
        "gate": "STAGE0_PASS" if stage0_pass else (
            "STAGE0_FAIL" if mode == "recorded" else "REAL_PILOT_OBSERVED"
        ),
        "stage0_checks": stage0_checks,
        "metrics": {
            "sections": len(sections),
            "committed": sum(bool(item.get("committed")) for item in sections),
            "contract_pass_rate": _rate(len(accepted), len(sections)),
            "repair_rate": _rate(len(repaired), len(sections)),
            "repair_success_rate": _rate(len(repaired_and_accepted), len(repaired)),
            "hard_rejects": int(summary.get("hard_rejects", 0)),
            "state_conflicts": sum(
                int(item.get("state_conflict_count", 0)) for item in sections
            ),
            "max_active_threads": max(
                (int(item.get("threads_open", 0)) for item in sections), default=0
            ),
            "final_memory_records": int(
                sections[-1].get("memory_records_total", 0) if sections else 0
            ),
            "mean_opening_overlap": round(
                mean(float(item.get("opening_overlap", 0.0)) for item in sections), 4
            )
            if sections
            else 0.0,
            "mean_consecutive_ngram_overlap": round(
                mean(
                    float(item.get("consecutive_ngram_overlap", 0.0))
                    for item in sections
                ),
                4,
            )
            if sections
            else 0.0,
            "total_tokens": sum(int(item.get("total_tokens", 0)) for item in sections),
            "mean_latency_seconds": round(
                mean(float(item.get("latency_seconds", 0.0)) for item in sections), 4
            )
            if sections
            else 0.0,
            "provider_errors": sum(
                int(item.get("provider_errors", 0)) for item in sections
            )
            + int(summary.get("provider_errors", 0)),
            "runtime_rebuilds": int(summary.get("runtime_rebuilds", 0)),
        },
        "real_sample_violation_counts": dict(violations.most_common()),
        "evidence_boundary": report.get("evidence_boundary", {}),
    }
    return analysis


def render_markdown(analysis: dict[str, Any]) -> str:
    metrics = analysis["metrics"]
    checks = analysis["stage0_checks"]
    lines = [
        f"# Author Long-Run Analysis: {analysis['run_id']}",
        "",
        f"Gate: `{analysis['gate']}`",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in metrics.items())
    lines.extend(
        [
            "",
            "## Stage 0 checks",
            "",
            "| Check | Result |",
            "| --- | --- |",
        ]
    )
    lines.extend(
        f"| {key} | {'PASS' if value else 'FAIL'} |" for key, value in checks.items()
    )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "This report preserves the source run's deterministic, recorded, real-provider, "
            "human-review, and LLM-judge flags. Unexecuted evidence types are not inferred.",
            "",
            "```json",
            json.dumps(analysis["evidence_boundary"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    analysis = analyze(report)
    out_json = args.out_json or args.report.with_name("analysis.json")
    out_md = args.out_md or args.report.with_name("analysis.md")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    out_md.write_text(render_markdown(analysis), encoding="utf-8")
    print(json.dumps({"gate": analysis["gate"], "out": str(out_json)}, ensure_ascii=False))
    return 0 if analysis["gate"] != "STAGE0_FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
