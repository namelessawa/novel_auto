"""Run and checkpoint the 3-theme × 5-style × 3-section real Stage 1 matrix."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(ROOT / "scripts")]


DEFAULT_THEMES = ("reality_mystery", "action_conflict", "warm_relationship")
DEFAULT_STYLES = (
    "literary",
    "noir_cold",
    "warm_healing",
    "hot_blooded",
    "classical_chapter",
)


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _combo_namespaces(
    *,
    base: str,
    themes: tuple[str, ...],
    styles: tuple[str, ...],
) -> dict[tuple[str, str], str]:
    values = {
        (theme, style): "_".join(item for item in (base, theme, style) if item)
        for theme in themes
        for style in styles
    }
    if any(
        not value or re.fullmatch(r"[a-z0-9_]+", value) is None
        for value in values.values()
    ):
        raise ValueError("derived id namespace must match [a-z0-9_]+")
    if len(values) != len(set(values.values())):
        raise ValueError("theme/style values produce duplicate id namespaces")
    return values


def _identity(
    *,
    themes: tuple[str, ...],
    styles: tuple[str, ...],
    seed: int,
    provider: str,
    model: str,
    thinking_mode: str,
    sections_per_combo: int,
    desired_length: int,
    checkpoint_every: int,
    runtime_rebuild_every: int,
    id_namespace: str = "",
) -> dict[str, Any]:
    return {
        "themes": list(themes),
        "styles": list(styles),
        "seed": seed,
        "provider": provider,
        "model": model,
        "thinking_mode": thinking_mode,
        "sections_per_combo": sections_per_combo,
        "desired_length": desired_length,
        "checkpoint_every": checkpoint_every,
        "runtime_rebuild_every": runtime_rebuild_every,
        "id_namespace": id_namespace,
    }


def _combo_integrity(report: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    attempted = list(report.get("sections", []))
    committed = [item for item in report.get("sections", []) if item.get("committed")]
    section_ids = [str(item.get("section_id")) for item in committed]
    transaction_ids = [str(item.get("transaction_id")) for item in attempted]
    revisions = [int(item.get("canonical_revision", 0)) for item in committed]
    if len(section_ids) != len(set(section_ids)):
        problems.append("duplicate_committed_section_id")
    if len(transaction_ids) != len(set(transaction_ids)):
        problems.append("duplicate_committed_transaction_id")
    if revisions != list(range(2, 2 + len(revisions))):
        problems.append("canonical_revision_not_contiguous")
    for previous, current in zip(attempted, attempted[1:]):
        if int(previous.get("canonical_revision_after", 0)) != int(
            current.get("canonical_revision_before", -1)
        ):
            problems.append("canonical_revision_chain_broken")
            break
    if any(
        int(item.get("canonical_revision_after", 0))
        != int(item.get("canonical_revision_before", 0))
        + int(bool(item.get("committed")))
        for item in attempted
    ):
        problems.append("canonical_revision_jump")
    if len(
        {
            int(item.get("story_bible_revision", 0))
            for item in attempted
        }
    ) > 1:
        problems.append("story_bible_revision_changed")
    if any(
        not item.get("narrative_contract_pass")
        or int(item.get("state_conflict_count", 0))
        for item in committed
    ):
        problems.append("hard_fact_error_committed")
    return problems


def aggregate(
    matrix: dict[str, Any], *, expected_combinations: int, sections_per_combo: int
) -> dict[str, Any]:
    combinations = matrix.get("combinations", [])
    sections = [
        section
        for combination in combinations
        for section in combination.get("sections", [])
    ]
    failures = [
        failure
        for combination in combinations
        for failure in combination.get("failures", [])
    ]
    attempted = len(sections)
    committed = sum(bool(item.get("committed")) for item in sections)
    contract_pass = sum(bool(item.get("narrative_contract_pass")) for item in sections)
    repaired = [item for item in sections if item.get("repair_performed")]
    repair_success = sum(bool(item.get("repair_success")) for item in repaired)
    writer_first_pass_count = sum(
        bool(item.get("writer_first_pass_pass")) for item in sections
    )
    writer_first_pass_rate = (
        round(writer_first_pass_count / attempted, 4) if attempted else 0.0
    )
    chapter_plan_success_count = sum(
        bool(item.get("chapter_plan_success")) for item in sections
    )
    chapter_plan_success_rate = (
        round(chapter_plan_success_count / attempted, 4) if attempted else 0.0
    )
    writer_plan_follow_count = sum(
        bool(item.get("writer_plan_followed")) for item in sections
    )
    writer_plan_follow_rate = (
        round(writer_plan_follow_count / attempted, 4) if attempted else 0.0
    )
    first_pass_after_plan_count = sum(
        bool(item.get("first_pass_after_plan")) for item in sections
    )
    first_pass_after_plan_rate = (
        round(first_pass_after_plan_count / attempted, 4) if attempted else 0.0
    )
    integrity = [
        {"run_id": item.get("run_id"), "problems": item.get("integrity", [])}
        for item in combinations
        if item.get("integrity")
    ]
    integrity_codes = Counter(
        code
        for item in combinations
        for code in item.get("integrity", [])
    )
    expected_sections = expected_combinations * sections_per_combo
    all_combinations = len(combinations) == expected_combinations
    contract_rate = round(contract_pass / attempted, 4) if attempted else 0.0
    repair_success_rate = (
        round(repair_success / len(repaired), 4) if repaired else 1.0
    )
    average_narrative_length = (
        round(
            sum(int(item.get("narrative_length", 0)) for item in sections)
            / attempted,
            2,
        )
        if attempted
        else 0.0
    )
    length_in_range_count = sum(
        900 <= int(item.get("narrative_length", 0)) <= 1100
        for item in sections
    )
    length_in_range_rate = (
        round(length_in_range_count / attempted, 4) if attempted else 0.0
    )
    hard_rejects = sum(
        int(item.get("summary", {}).get("hard_rejects", 0))
        for item in combinations
    )
    reported_provider_errors = sum(
        int(item.get("summary", {}).get("provider_errors", 0))
        for item in combinations
    )
    observed_provider_errors = sum(
        bool(item.get("provider_failure")) for item in failures
    )
    provider_errors = max(reported_provider_errors, observed_provider_errors)
    hard_fact_error_commits = sum(
        bool(item.get("committed"))
        and (
            not item.get("narrative_contract_pass")
            or int(item.get("state_conflict_count", 0)) > 0
        )
        for item in sections
    )
    state_conflict_commits = sum(
        bool(item.get("committed")) and int(item.get("state_conflict_count", 0)) > 0
        for item in sections
    )
    illegal_thread_change_commits = sum(
        int(item.get("illegal_thread_change_commits", 0))
        for item in sections
        if item.get("committed")
    )
    evidenceless_state_delta_commits = sum(
        int(item.get("evidenceless_state_delta_commits", 0))
        for item in sections
        if item.get("committed")
    )
    common_checks = {
        "all_combinations_completed": all_combinations,
        "all_attempts_completed": attempted == expected_sections,
        "hard_fact_error_commits_zero": hard_fact_error_commits == 0,
        "state_conflict_commits_zero": state_conflict_commits == 0,
        "transaction_data_corruption_zero": not integrity,
        "revision_jumps_zero": not any(
            code in integrity_codes
            for code in (
                "canonical_revision_not_contiguous",
                "canonical_revision_chain_broken",
                "canonical_revision_jump",
            )
        ),
        "duplicate_sections_zero": (
            integrity_codes["duplicate_committed_section_id"] == 0
        ),
        "duplicate_transactions_zero": (
            integrity_codes["duplicate_committed_transaction_id"] == 0
        ),
        "story_bible_revision_stable": (
            integrity_codes["story_bible_revision_changed"] == 0
        ),
        "provider_errors_zero": provider_errors == 0,
        "provider_error_accounting_matches": (
            reported_provider_errors == observed_provider_errors
        ),
        "chapter_plan_success_at_least_95pct": (
            chapter_plan_success_rate >= 0.95
        ),
        "illegal_thread_change_commits_zero": (
            illegal_thread_change_commits == 0
        ),
        "evidenceless_state_delta_commits_zero": (
            evidenceless_state_delta_commits == 0
        ),
    }
    complete = all_combinations and attempted == expected_sections
    g1_single = expected_combinations == 1 and expected_sections == 1
    mini_matrix = expected_combinations == 5 and expected_sections == 15
    if g1_single:
        gate_checks = {
            **common_checks,
            "committed_exactly_1": committed == 1,
            "contract_accepted_exactly_1": contract_pass == 1,
            "repair_after_accepted_exactly_100pct": repair_success_rate == 1.0,
            "length_900_1100_exactly_1": length_in_range_count == 1,
        }
        gate = "G1_SINGLE_PASS" if complete and all(gate_checks.values()) else (
            "G1_SINGLE_FAIL" if complete else "G1_SINGLE_INCOMPLETE"
        )
    elif mini_matrix:
        gate_checks = {
            **common_checks,
            "committed_at_least_14_of_15": committed >= 14,
            "writer_first_pass_at_least_9_of_15": writer_first_pass_count >= 9,
            "contract_accepted_at_least_93pct": contract_rate >= 0.93,
            "repair_after_accepted_at_least_90pct": repair_success_rate >= 0.90,
            "length_900_1100_at_least_93pct": length_in_range_rate >= 0.93,
            "repair_rate_at_most_40pct": (
                (len(repaired) / attempted if attempted else 0.0) <= 0.40
            ),
        }
        gate = "MINI_MATRIX_PASS" if complete and all(gate_checks.values()) else (
            "MINI_MATRIX_FAIL" if complete else "MINI_MATRIX_INCOMPLETE"
        )
    else:
        gate_checks = {
            **common_checks,
            "committed_at_least_43_of_45": committed >= 43,
            "contract_accepted_at_least_95pct": contract_rate >= 0.95,
            "repair_after_accepted_at_least_90pct": repair_success_rate >= 0.90,
            "repair_rate_at_most_40pct": (
                (len(repaired) / attempted if attempted else 0.0) <= 0.40
            ),
        }
        gate = "STAGE1_PASS" if complete and all(gate_checks.values()) else (
            "STAGE1_FAIL" if complete else "STAGE1_INCOMPLETE"
        )
    return {
        "gate": gate,
        "gate_checks": gate_checks,
        "expected_combinations": expected_combinations,
        "completed_combinations": len(combinations),
        "expected_sections": expected_sections,
        "attempted": attempted,
        "committed": committed,
        "rejected": attempted - committed,
        "contract_pass": contract_pass,
        "contract_pass_rate": contract_rate,
        "writer_first_pass_pass": writer_first_pass_count,
        "writer_first_pass_rate": writer_first_pass_rate,
        "chapter_plan_success": chapter_plan_success_count,
        "chapter_plan_success_rate": chapter_plan_success_rate,
        "writer_plan_followed": writer_plan_follow_count,
        "writer_plan_follow_rate": writer_plan_follow_rate,
        "first_pass_after_plan": first_pass_after_plan_count,
        "first_pass_after_plan_rate": first_pass_after_plan_rate,
        "writer_retries": sum(
            bool(item.get("writer_retry_performed")) for item in sections
        ),
        "repairs": len(repaired),
        "repair_rate": round(len(repaired) / attempted, 4) if attempted else 0.0,
        "repair_success": repair_success,
        "repair_success_rate": repair_success_rate,
        "average_narrative_length": average_narrative_length,
        "length_in_range_count": length_in_range_count,
        "length_in_range_rate": length_in_range_rate,
        "expand_patch_count": sum(
            int(item.get("repair_patch_expand_count", 0)) for item in sections
        ),
        "compact_patch_count": sum(
            int(item.get("repair_patch_compact_count", 0)) for item in sections
        ),
        "hard_rejects": hard_rejects,
        "hard_fact_error_commits": hard_fact_error_commits,
        "state_conflict_commits": state_conflict_commits,
        "illegal_thread_change_commits": illegal_thread_change_commits,
        "evidenceless_state_delta_commits": evidenceless_state_delta_commits,
        "data_integrity_violations": integrity,
        "data_integrity_violation_codes": dict(integrity_codes.most_common()),
        "provider_errors": provider_errors,
        "provider_error_rows": observed_provider_errors,
        "provider_calls": (
            sum(
                int(item.get("writer_calls", 0))
                + int(item.get("structured_output_repair_count", 0))
                + int(item.get("planner_calls", 0))
                for item in sections
            )
            + sum(
                int(failure.get("provider_call_count", 0))
                for failure in failures
            )
        ),
        "planner_calls": (
            sum(int(item.get("planner_calls", 0)) for item in sections)
            + sum(int(item.get("planner_calls", 0)) for item in failures)
        ),
        "planner_tokens": sum(
            int(item.get("planner_tokens", 0)) for item in sections
        ),
        "prompt_tokens": sum(int(item.get("prompt_tokens", 0)) for item in sections),
        "completion_tokens": sum(
            int(item.get("completion_tokens", 0)) for item in sections
        ),
        "repair_tokens": sum(int(item.get("repair_tokens", 0)) for item in sections),
        "retry_tokens": sum(int(item.get("retry_tokens", 0)) for item in sections),
        "total_tokens": sum(int(item.get("total_tokens", 0)) for item in sections),
        "required_events_completed": sum(
            int(item.get("required_events_completed", 0)) for item in sections
        ),
        "required_events_total": sum(
            int(item.get("required_events_total", 0)) for item in sections
        ),
        "end_states_reached": sum(
            int(item.get("end_states_reached", 0)) for item in sections
        ),
        "end_states_total": sum(
            int(item.get("end_states_total", 0)) for item in sections
        ),
        "dropped_delta_count": sum(
            int(item.get("dropped_delta_count", 0)) for item in sections
        ),
        "dropped_thread_change_count": sum(
            int(item.get("dropped_thread_change_count", 0)) for item in sections
        ),
        "mean_latency_seconds": round(
            sum(float(item.get("latency_seconds", 0.0)) for item in sections)
            / attempted,
            4,
        )
        if attempted
        else 0.0,
    }


def _combination_record(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": report["run_id"],
        "theme": report["config"]["theme"],
        "style": report["config"]["style"],
        "summary": report["summary"],
        "integrity": _combo_integrity(report),
        "sections": report["sections"],
        "failures": report.get("failures", []),
    }


def _render_markdown(matrix: dict[str, Any]) -> str:
    summary = matrix["summary"]
    lines = [
        "# Author Stage 1 Real Matrix",
        "",
        f"Gate: `{summary['gate']}`",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Combinations",
        "",
        "| Theme | Style | Attempted | Committed | First pass | Contract | Repair | Reject | Tokens | Integrity |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in matrix.get("combinations", []):
        combo = item["summary"]
        lines.append(
            "| {theme} | {style} | {attempted} | {committed} | {first_pass} | {contract_pass} | "
            "{repairs} | {hard_rejects} | {total_tokens} | {integrity} |".format(
                theme=item["theme"],
                style=item["style"],
                attempted=combo.get("attempted", 0),
                committed=combo.get("committed", 0),
                first_pass=combo.get("writer_first_pass_pass", 0),
                contract_pass=combo.get("contract_pass", 0),
                repairs=combo.get("repairs", 0),
                hard_rejects=combo.get("hard_rejects", 0),
                total_tokens=combo.get("total_tokens", 0),
                integrity=",".join(item.get("integrity", [])) or "OK",
            )
        )
    lines.extend(
        [
            "",
            "Evidence boundary: real provider execution; no human review or LLM judge. "
            "Deterministic contract and transaction gates remain authoritative.",
            "",
        ]
    )
    return "\n".join(lines)


def _save(matrix: dict[str, Any], output_dir: Path) -> None:
    expected = len(matrix["config"]["themes"]) * len(matrix["config"]["styles"])
    matrix["summary"] = aggregate(
        matrix,
        expected_combinations=expected,
        sections_per_combo=int(matrix["config"]["sections_per_combo"]),
    )
    matrix["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    rendered = json.dumps(matrix, ensure_ascii=False)
    from nf_core.provider_runtime import get_stage_provider_config

    stage_config = get_stage_provider_config()
    secret = stage_config.api_key if stage_config is not None else ""
    if secret and secret in rendered:
        raise RuntimeError("credential leak guard rejected Stage 1 matrix report")
    json_path = output_dir / "stage1-matrix.json"
    json_partial = json_path.with_suffix(".json.partial")
    json_partial.write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(json_partial, json_path)
    markdown = output_dir / "stage1-matrix.md"
    partial = markdown.with_suffix(".md.partial")
    partial.write_text(_render_markdown(matrix), encoding="utf-8")
    os.replace(partial, markdown)


async def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    # Import-order barrier: parse and bind the read-only provider file before
    # importing the author runtime, Writer, or llm_client.
    from validate_styles import configure_provider_runtime

    provider = configure_provider_runtime(args.provider_file.resolve())
    if args.model and args.model != provider.model:
        raise ValueError(
            "--model cannot override the model in the read-only provider file"
        )
    from nf_core.llm_client import llm_client
    from nf_core.provider_runtime import stage_provider_scope

    with stage_provider_scope(provider):
        # Second barrier: retire any client created by an in-process importer.
        llm_client.reload(config=provider)
        try:
            return await _run_matrix_configured(args, provider)
        finally:
            await llm_client.aclose()


async def _run_matrix_configured(
    args: argparse.Namespace,
    provider,
) -> dict[str, Any]:
    from run_author_longrange import RunLimits, run_sequence

    id_namespace = str(args.id_namespace or "").strip().lower()
    if id_namespace and re.fullmatch(r"[a-z0-9_]+", id_namespace) is None:
        raise ValueError("--id-namespace must match [a-z0-9_]+")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    themes = _split_csv(args.themes)
    styles = _split_csv(args.styles)
    combo_namespaces = _combo_namespaces(
        base=id_namespace,
        themes=themes,
        styles=styles,
    )
    model = provider.model
    identity = _identity(
        themes=themes,
        styles=styles,
        seed=args.seed,
        provider=provider.provider,
        model=model,
        thinking_mode=provider.thinking_mode,
        sections_per_combo=args.sections_per_combo,
        desired_length=args.desired_length,
        checkpoint_every=args.checkpoint_every,
        runtime_rebuild_every=args.runtime_rebuild_every,
        id_namespace=id_namespace,
    )
    matrix_path = output_dir / "stage1-matrix.json"
    if args.resume and matrix_path.is_file():
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        actual = {key: matrix.get("config", {}).get(key) for key in identity}
        if actual != identity:
            raise ValueError("Stage 1 resume identity does not match the existing matrix")
    else:
        matrix = {
            "schema_version": 1,
            "stage": "stage1_real_matrix",
            "config": identity,
            "evidence_boundary": {
                "deterministic": True,
                "recorded": False,
                "real_provider": True,
                "human_review": False,
                "llm_judge": False,
            },
            "combinations": [],
            "summary": {},
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    completed = {
        (str(item["theme"]), str(item["style"]))
        for item in matrix["combinations"]
        if int(item.get("summary", {}).get("attempted", 0))
        >= args.sections_per_combo
    }
    for theme in themes:
        for style in styles:
            if (theme, style) in completed:
                continue
            run_dir = output_dir / "runs" / f"{theme}__{style}"
            combo_resume = (run_dir / "report.json").is_file()
            report: dict[str, Any] | None = None
            for _ in range(args.combo_retries + 1):
                report = await run_sequence(
                    output_dir=run_dir,
                    mode="real",
                    style=style,
                    theme=theme,
                    seed=args.seed,
                    desired_length=args.desired_length,
                    checkpoint_every=args.checkpoint_every,
                    limits=RunLimits(
                        max_sections=args.sections_per_combo,
                        max_total_tokens=0,
                        max_cost=0.0,
                        prompt_cost_per_million=args.prompt_cost_per_million,
                        completion_cost_per_million=args.completion_cost_per_million,
                    ),
                    resume=combo_resume,
                    provider=provider.provider,
                    model=model,
                    runtime_rebuild_every=(
                        None
                        if args.runtime_rebuild_every <= 0
                        else args.runtime_rebuild_every
                    ),
                    inject_failure=args.inject_failure,
                    stop_on_gate_failure=args.stop_on_gate_failure,
                    id_namespace=combo_namespaces[(theme, style)],
                )
                combo_resume = True
                if report["summary"].get("stop_reason") != "generation_error":
                    break
            assert report is not None
            record = _combination_record(report)
            matrix["combinations"] = [
                item
                for item in matrix["combinations"]
                if (item["theme"], item["style"]) != (theme, style)
            ]
            matrix["combinations"].append(record)
            _save(matrix, output_dir)
            print(
                json.dumps(
                    {
                        "combination": f"{theme}__{style}",
                        "completed": len(matrix["combinations"]),
                        "attempted": record["summary"].get("attempted", 0),
                        "committed": record["summary"].get("committed", 0),
                        "tokens": record["summary"].get("total_tokens", 0),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if args.stop_on_gate_failure and (
                record["integrity"]
                or record["summary"].get("provider_errors", 0)
                or record["summary"].get("stop_reason")
            ):
                return matrix
    _save(matrix, output_dir)
    return matrix


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--provider-file", type=Path, default=ROOT / "coding.txt")
    parser.add_argument("--model", default="")
    parser.add_argument("--id-namespace", default="")
    parser.add_argument("--themes", default=",".join(DEFAULT_THEMES))
    parser.add_argument("--styles", default=",".join(DEFAULT_STYLES))
    parser.add_argument("--sections-per-combo", type=int, default=3)
    parser.add_argument("--checkpoint-every", type=int, default=1)
    parser.add_argument("--runtime-rebuild-every", type=int, default=1)
    parser.add_argument("--inject-failure", default="")
    parser.add_argument("--stop-on-gate-failure", action="store_true")
    parser.add_argument("--combo-retries", type=int, default=1)
    parser.add_argument("--desired-length", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260722)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prompt-cost-per-million", type=float, default=0.0)
    parser.add_argument("--completion-cost-per-million", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.sections_per_combo = max(1, args.sections_per_combo)
    args.checkpoint_every = max(1, args.checkpoint_every)
    args.combo_retries = max(0, args.combo_retries)
    args.desired_length = max(200, args.desired_length)
    matrix = asyncio.run(run_matrix(args))
    print(json.dumps(matrix["summary"], ensure_ascii=False, indent=2))
    return 0 if matrix["summary"]["gate"] in {
        "G1_SINGLE_PASS",
        "MINI_MATRIX_PASS",
        "STAGE1_PASS",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
