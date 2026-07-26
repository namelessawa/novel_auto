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


def _analyze_single(report: dict[str, Any]) -> dict[str, Any]:
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


def _section_codes(section: dict[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *section.get("narrative_violation_codes", []),
                *section.get("state_violation_codes", []),
                *section.get("repair_patch_codes", []),
            ]
        )
    )


def _observed_codes(section: dict[str, Any]) -> list[str]:
    histories = [
        *section.get("narrative_validation_history_codes", []),
        *section.get("state_validation_history_codes", []),
    ]
    return list(
        dict.fromkeys(
            [
                *_section_codes(section),
                *(
                    code
                    for history in histories
                    for code in history
                ),
                *section.get("proposal_drop_codes", []),
                *section.get("repair_audit_codes", []),
            ]
        )
    )


def _group_metrics(
    sections: list[dict[str, Any]],
    *,
    group_key: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for section in sections:
        grouped.setdefault(str(section.get(group_key, "")), []).append(section)
    result: dict[str, dict[str, Any]] = {}
    for key, values in sorted(grouped.items()):
        repairs = [item for item in values if item.get("repair_performed")]
        repair_success = sum(bool(item.get("repair_success")) for item in repairs)
        rejected = [item for item in values if not item.get("committed")]
        result[key] = {
            "attempted": len(values),
            "committed": sum(bool(item.get("committed")) for item in values),
            "success_rate": _rate(
                sum(bool(item.get("committed")) for item in values),
                len(values),
            ),
            "repairs": len(repairs),
            "repair_rate": _rate(len(repairs), len(values)),
            "repair_success": repair_success,
            "repair_success_rate": _rate(repair_success, len(repairs)),
            "contract_pass": sum(
                bool(item.get("narrative_contract_pass")) for item in values
            ),
            "style_drift_warnings": sum(
                bool(item.get("style_drift_warning")) for item in values
            ),
            "failure_codes": dict(
                Counter(
                    code
                    for item in rejected
                    for code in _observed_codes(item)
                ).most_common()
            ),
            "observed_codes": dict(
                Counter(
                    code
                    for item in values
                    for code in _observed_codes(item)
                ).most_common()
            ),
            "total_tokens": sum(
                int(item.get("total_tokens", 0)) for item in values
            ),
            "mean_latency_seconds": round(
                mean(float(item.get("latency_seconds", 0.0)) for item in values),
                4,
            )
            if values
            else 0.0,
        }
    return result


def _analyze_matrix(report: dict[str, Any]) -> dict[str, Any]:
    combinations = report.get("combinations", [])
    sections: list[dict[str, Any]] = []
    for combination in combinations:
        for ordinal, source in enumerate(combination.get("sections", []), start=1):
            section = dict(source)
            section["theme"] = combination.get("theme", "")
            section["style"] = combination.get("style", "")
            section["run_id"] = combination.get("run_id", "")
            section["ordinal"] = ordinal
            sections.append(section)

    summary = report.get("summary", {})
    repaired = [item for item in sections if item.get("repair_performed")]
    rejected = [item for item in sections if not item.get("committed")]
    mainline_warnings: list[str] = []
    active_thread_warnings: list[dict[str, Any]] = []
    first_to_third_eligible = 0
    first_to_third_hits = 0
    for combination in combinations:
        values = combination.get("sections", [])
        if len(values) >= 3 and all(
            not item.get("main_conflict_progress") for item in values[:3]
        ):
            mainline_warnings.append(str(combination.get("run_id", "")))
        for item in values:
            if int(item.get("threads_open", 0)) > 12:
                active_thread_warnings.append(
                    {
                        "run_id": combination.get("run_id", ""),
                        "section_id": item.get("section_id", ""),
                        "active_threads": item.get("threads_open", 0),
                    }
                )
        if len(values) >= 3:
            first_ids = set(values[0].get("memory_record_ids_added", []))
            third_ids = set(values[2].get("memory_selected_ids", []))
            if first_ids:
                first_to_third_eligible += 1
                first_to_third_hits += int(bool(first_ids & third_ids))

    ordinal_trend: dict[str, dict[str, Any]] = {}
    for ordinal in (1, 2, 3):
        values = [
            item for item in sections if int(item.get("ordinal", 0)) == ordinal
        ]
        ordinal_trend[str(ordinal)] = {
            "sections": len(values),
            "mean_tokens": round(
                mean(int(item.get("total_tokens", 0)) for item in values), 2
            )
            if values
            else 0.0,
            "mean_latency_seconds": round(
                mean(float(item.get("latency_seconds", 0.0)) for item in values),
                4,
            )
            if values
            else 0.0,
            "repairs": sum(bool(item.get("repair_performed")) for item in values),
            "mean_ngram_overlap": round(
                mean(
                    float(item.get("consecutive_ngram_overlap", 0.0))
                    for item in values
                ),
                4,
            )
            if values
            else 0.0,
        }

    style_risk_codes = {
        "hot_blooded": (
            "CASUALTY",
            "INJURY",
            "BACKSTORY",
            "FORBIDDEN_OUTCOME",
        ),
        "classical_chapter": (
            "CHARACTER_ADDED",
            "ORGANIZATION_ADDED",
            "DATE",
            "BACKSTORY",
        ),
        "warm_healing": ("CAUSAL_LINK_WEAKENED",),
        "noir_cold": ("TIME_", "CAUSAL_LINK_WEAKENED"),
    }
    style_risk_observations: dict[str, dict[str, int]] = {}
    for style, needles in style_risk_codes.items():
        counter = Counter(
            code
            for item in sections
            if item.get("style") == style
            for code in _observed_codes(item)
            if any(needle in code for needle in needles)
        )
        style_risk_observations[style] = dict(counter.most_common())

    continuity = {
        "character_continuity_errors": sum(
            int(item.get("character_continuity_errors", 0))
            for item in sections
        ),
        "knowledge_boundary_errors": sum(
            int(item.get("knowledge_boundary_errors", 0))
            for item in sections
        ),
        "relationship_conflicts": sum(
            int(item.get("relationship_conflicts", 0)) for item in sections
        ),
        "item_owner_conflict": sum(
            int(item.get("item_owner_conflict", 0)) for item in sections
        ),
        "item_state_conflict": sum(
            int(item.get("item_state_conflict", 0)) for item in sections
        ),
        "threads_opened": sum(
            int(item.get("threads_opened_count", 0)) for item in sections
        ),
        "threads_advanced": sum(
            int(item.get("threads_advanced_count", 0)) for item in sections
        ),
        "threads_resolved": sum(
            int(item.get("threads_resolved_count", 0)) for item in sections
        ),
        "max_active_thread_count": max(
            (int(item.get("threads_open", 0)) for item in sections),
            default=0,
        ),
        "no_mainline_progress_three_section_warnings": mainline_warnings,
        "active_threads_over_12_warnings": active_thread_warnings,
        "memory_records_final_total": sum(
            int(combination.get("sections", [])[-1].get(
                "memory_records_total", 0
            ))
            for combination in combinations
            if combination.get("sections")
        ),
        "memory_selected_total": sum(
            int(item.get("memory_records_selected", 0)) for item in sections
        ),
        "memory_reference_hit_sections": sum(
            bool(item.get("memory_reference_hit")) for item in sections
        ),
        "first_to_third_memory_selection_hits": first_to_third_hits,
        "first_to_third_memory_selection_eligible": first_to_third_eligible,
        "first_to_third_memory_selection_rate": _rate(
            first_to_third_hits,
            first_to_third_eligible,
        ),
        "style_contract_pass": sum(
            item.get("style_contract_pass") is True for item in sections
        ),
        "style_drift_warnings": sum(
            bool(item.get("style_drift_warning")) for item in sections
        ),
        "style_risk_observations": style_risk_observations,
        "mean_opening_overlap": round(
            mean(float(item.get("opening_overlap", 0.0)) for item in sections),
            4,
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
        "max_consecutive_ngram_overlap": max(
            (
                float(item.get("consecutive_ngram_overlap", 0.0))
                for item in sections
            ),
            default=0.0,
        ),
    }
    metrics = {
        "attempted": len(sections),
        "committed": sum(bool(item.get("committed")) for item in sections),
        "rejected": len(rejected),
        "contract_pass": sum(
            bool(item.get("narrative_contract_pass")) for item in sections
        ),
        "contract_pass_rate": _rate(
            sum(bool(item.get("narrative_contract_pass")) for item in sections),
            len(sections),
        ),
        "repairs": len(repaired),
        "repair_rate": _rate(len(repaired), len(sections)),
        "repair_success": sum(
            bool(item.get("repair_success")) for item in repaired
        ),
        "repair_success_rate": _rate(
            sum(bool(item.get("repair_success")) for item in repaired),
            len(repaired),
        ),
        "prompt_tokens": sum(
            int(item.get("prompt_tokens", 0)) for item in sections
        ),
        "completion_tokens": sum(
            int(item.get("completion_tokens", 0)) for item in sections
        ),
        "repair_tokens": sum(
            int(item.get("repair_tokens", 0)) for item in sections
        ),
        "total_tokens": sum(
            int(item.get("total_tokens", 0)) for item in sections
        ),
        "provider_calls": sum(
            int(item.get("writer_calls", 0)) for item in sections
        ),
        "provider_errors": int(summary.get("provider_errors", 0)),
        "mean_latency_seconds": round(
            mean(float(item.get("latency_seconds", 0.0)) for item in sections),
            4,
        )
        if sections
        else 0.0,
    }
    failure_cases = [
        {
            "run_id": item.get("run_id", ""),
            "theme": item.get("theme", ""),
            "style": item.get("style", ""),
            "section_id": item.get("section_id", ""),
            "transaction_id": item.get("transaction_id", ""),
            "validator_codes": _section_codes(item),
            "observed_codes": _observed_codes(item),
            "repair_patch_count": item.get("repair_patch_count", 0),
            "repair_patch_types": item.get("repair_patch_types", []),
            "repair_patch_codes": item.get("repair_patch_codes", []),
            "final_phase": item.get("phase", ""),
        }
        for item in rejected
    ]
    return {
        "schema_version": 2,
        "run_id": "stage1-full-matrix",
        "source_stage": report.get("stage", ""),
        "gate": summary.get("gate", "STAGE1_INCOMPLETE"),
        "gate_checks": summary.get("gate_checks", {}),
        "metrics": metrics,
        "by_theme": _group_metrics(sections, group_key="theme"),
        "by_style": _group_metrics(sections, group_key="style"),
        "continuity": continuity,
        "token_and_repetition_trend": ordinal_trend,
        "failure_cases": failure_cases,
        "sections": sections,
        "evidence_boundary": report.get("evidence_boundary", {}),
        "limitations": [
            "Memory recall is a deterministic context-selection proxy, not semantic human review.",
            "Style findings are existing deterministic observations; no LLM judge was used.",
            "Three-section combinations do not prove unlimited long-form stability.",
        ],
    }


def analyze(report: dict[str, Any]) -> dict[str, Any]:
    if "combinations" in report:
        return _analyze_matrix(report)
    return _analyze_single(report)


def _render_matrix_markdown(analysis: dict[str, Any]) -> str:
    metrics = analysis["metrics"]
    continuity = analysis["continuity"]
    lines = [
        "# Stage 1 Full Matrix Deterministic Analysis",
        "",
        f"Gate: `{analysis['gate']}`",
        "",
        "## Overall",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in metrics.items())
    for title, key in (("By theme", "by_theme"), ("By style", "by_style")):
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| Key | Attempted | Committed | Success | Repairs | Repair success | Drift | Failure codes |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for name, item in analysis[key].items():
            lines.append(
                "| {name} | {attempted} | {committed} | {success:.2%} | "
                "{repairs} | {repair_success:.2%} | {drift} | {codes} |".format(
                    name=name,
                    attempted=item["attempted"],
                    committed=item["committed"],
                    success=item["success_rate"],
                    repairs=item["repairs"],
                    repair_success=item["repair_success_rate"],
                    drift=item["style_drift_warnings"],
                    codes=json.dumps(
                        item["failure_codes"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            )
    lines.extend(
        [
            "",
            "## Continuity",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
        ]
    )
    for key, value in continuity.items():
        rendered = (
            json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if isinstance(value, (dict, list))
            else value
        )
        lines.append(f"| {key} | {rendered} |")
    lines.extend(
        [
            "",
            "## Token and repetition trend",
            "",
            "| Ordinal | Sections | Mean tokens | Mean latency | Repairs | Mean overlap |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for ordinal, item in analysis["token_and_repetition_trend"].items():
        lines.append(
            f"| {ordinal} | {item['sections']} | {item['mean_tokens']} | "
            f"{item['mean_latency_seconds']} | {item['repairs']} | "
            f"{item['mean_ngram_overlap']} |"
        )
    lines.extend(
        [
            "",
            "## 45-section detail",
            "",
            "| Theme | Style | # | Section | Commit | Contract | Repair | Patches | Revision | Tokens | Latency |",
            "| --- | --- | ---: | --- | --- | --- | --- | ---: | --- | ---: | ---: |",
        ]
    )
    for item in analysis["sections"]:
        lines.append(
            "| {theme} | {style} | {ordinal} | {section} | {commit} | "
            "{contract} | {repair} | {patches} | {before}→{after} | "
            "{tokens} | {latency} |".format(
                theme=item.get("theme", ""),
                style=item.get("style", ""),
                ordinal=item.get("ordinal", 0),
                section=item.get("section_id", ""),
                commit="PASS" if item.get("committed") else "REJECT",
                contract=(
                    "PASS"
                    if item.get("narrative_contract_pass")
                    else "FAIL"
                ),
                repair="yes" if item.get("repair_performed") else "no",
                patches=item.get("repair_patch_count", 0),
                before=item.get("canonical_revision_before", 0),
                after=item.get("canonical_revision_after", 0),
                tokens=item.get("total_tokens", 0),
                latency=item.get("latency_seconds", 0),
            )
        )
    lines.extend(["", "## Failure cases", ""])
    if analysis["failure_cases"]:
        lines.extend(
            [
                "| Run | Section | Codes | Patch | Result |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in analysis["failure_cases"]:
            lines.append(
                f"| {item['run_id']} | {item['section_id']} | "
                f"{','.join(item['validator_codes'])} | "
                f"{'/'.join(item['repair_patch_types']) or 'none'} | "
                f"{item['final_phase']} |"
            )
    else:
        lines.append("No rejected transactions.")
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            "```json",
            json.dumps(
                analysis["evidence_boundary"],
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in analysis["limitations"])
    lines.append("")
    return "\n".join(lines)


def render_markdown(analysis: dict[str, Any]) -> str:
    if analysis.get("source_stage") == "stage1_real_matrix":
        return _render_matrix_markdown(analysis)
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
    return (
        2
        if analysis["gate"]
        in {"STAGE0_FAIL", "STAGE1_FAIL", "STAGE1_INCOMPLETE"}
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
