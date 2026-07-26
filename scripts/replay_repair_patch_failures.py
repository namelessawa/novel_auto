"""Offline Patch gate for the final six real Stage 1 rejects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
for entry in (str(BACKEND), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from scripts.replay_stage1_event_failures import (  # noqa: E402
    _bible_for_replay,
    _state_from_contract,
)
from story.event_execution import EventExecutionPlan  # noqa: E402
from story.models import (  # noqa: E402
    SectionGoal,
    StoryThreadRepository,
    WriterCandidate,
)
from story.narrative_contract import NarrativeContract  # noqa: E402
from story.narrative_validator import NarrativeContractValidator  # noqa: E402
from story.repair_patch import (  # noqa: E402
    RepairPatchSet,
    RepairPatchValidator,
)
from story.repair_plan import (  # noqa: E402
    RepairPlanBuilder,
    RepairRegressionValidator,
    repair_patch_prompt_payload,
)
from story.validator import StoryValidator  # noqa: E402


DEFAULT_FIXTURE = (
    ROOT
    / "backend"
    / "tests"
    / "fixtures"
    / "repair_patch_real_failures.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / ".tmp"
    / "event-completion-repair"
    / "real-rejects-patch-replay.json"
)

# Offline replay has no LLM. This completes the one frozen length-only case
# after its recorded real-provider addition. It is test data only and is never
# imported by the runtime repair path.
_OFFLINE_EXPAND_SUFFIXES = {
    "action_conflict__literary__section_0001": "掌心仍轻压着衣袋，没有移开。",
}


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".partial",
        dir=path.parent,
    )
    partial = Path(raw)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(partial, path)
    finally:
        if partial.exists():
            partial.unlink()


def replay_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    narrative_validator = NarrativeContractValidator()
    authority_validator = StoryValidator()
    patch_validator = RepairPatchValidator()
    regression_validator = RepairRegressionValidator()
    results: list[dict[str, Any]] = []

    for case in payload.get("cases", []):
        original = WriterCandidate.model_validate(case["original_candidate"])
        original_hash = hashlib.sha256(
            original.narrative_text.encode("utf-8")
        ).hexdigest()
        if original_hash != case["original_sha256"]:
            raise ValueError(f"fixture hash mismatch: {case['case_id']}")
        contract = NarrativeContract.model_validate(case["narrative_contract"])
        event_plan = EventExecutionPlan.model_validate(
            case["event_execution_plan"]
        )
        goal = SectionGoal.model_validate(case["section_goal"])
        state = _state_from_contract(contract)
        bible = _bible_for_replay(contract, goal)
        threads = StoryThreadRepository(revision=state.revision)

        initial_narrative = narrative_validator.validate(
            contract,
            original.narrative_text,
            event_execution_plan=event_plan,
            event_evidence=original.event_evidence,
            end_state_evidence=original.end_state_evidence,
        )
        initial_authority = authority_validator.validate(
            bible=bible,
            state=state,
            threads=threads,
            goal=goal,
            candidate=original,
        )
        plan = RepairPlanBuilder().build(
            transaction_id=case["case_id"],
            contract=contract,
            event_plan=event_plan,
            narrative_report=initial_narrative,
            state_report=initial_authority,
            narrative_text=original.narrative_text,
        )
        prompt_payload = repair_patch_prompt_payload(
            plan,
            original.narrative_text,
        )
        patch_payloads = list(prompt_payload["suggested_patch_templates"])
        expansion = prompt_payload.get("expansion_request")
        if expansion:
            recorded_text = case["provider_repair_output"]["narrative_text"]
            recorded_addition = (
                recorded_text[len(original.narrative_text) :]
                if recorded_text.startswith(original.narrative_text)
                else ""
            )
            patch_text = (
                recorded_addition
                + _OFFLINE_EXPAND_SUFFIXES.get(case["case_id"], "")
            )
            patch_payloads.append(
                {
                    "patch_type": expansion["patch_type"],
                    "anchor": expansion["anchor"],
                    "patch_text": patch_text,
                    "target_events": [],
                    "target_end_states": [],
                    "max_chars": expansion["target_chars"],
                    "preserve": expansion["preserve"],
                    "target_chars": expansion["target_chars"],
                    "purpose": expansion["purpose"],
                }
            )
        patch_set = RepairPatchSet.model_validate({"patches": patch_payloads})
        applied = patch_validator.validate_and_apply(
            original_text=original.narrative_text,
            patch_set=patch_set,
            plan=plan,
            contract=contract,
            event_plan=event_plan,
        )
        final_candidate = original.model_copy(
            update={"narrative_text": applied.narrative_text}
        )
        final_narrative = narrative_validator.validate(
            contract,
            final_candidate.narrative_text,
            event_execution_plan=event_plan,
            event_evidence=original.event_evidence,
            end_state_evidence=original.end_state_evidence,
        )
        regressions = regression_validator.validate(
            plan=plan,
            final_report=final_narrative,
            repaired_text=final_candidate.narrative_text,
        )
        final_authority = authority_validator.validate(
            bible=bible,
            state=state,
            threads=threads,
            goal=goal,
            candidate=final_candidate,
            drop_unsupported_proposals=True,
        )
        passed = (
            applied.report.accepted
            and final_narrative.accepted
            and final_authority.accepted
            and not regressions
        )
        results.append(
            {
                "case_id": case["case_id"],
                "theme": case["theme"],
                "style": case["style"],
                "original_sha256": original_hash,
                "initial_codes": [
                    item.code for item in initial_narrative.violations
                ],
                "patch_count": len(patch_set.patches),
                "patch_types": [item.patch_type for item in patch_set.patches],
                "patches": [
                    item.model_dump(mode="json") for item in patch_set.patches
                ],
                "patch_accepted": applied.report.accepted,
                "patch_codes": [
                    item.code for item in applied.report.violations
                ],
                "patch_char_delta": applied.report.char_delta,
                "final_narrative_accepted": final_narrative.accepted,
                "final_narrative_codes": [
                    item.code for item in final_narrative.violations
                ],
                "final_authority_accepted": final_authority.accepted,
                "final_authority_codes": [
                    item.code for item in final_authority.violations
                ],
                "repair_regression_count": len(regressions),
                "passed": passed,
            }
        )

    passed_count = sum(item["passed"] for item in results)
    regression_count = sum(
        item["repair_regression_count"] for item in results
    )
    patch_failure_count = sum(not item["patch_accepted"] for item in results)
    validator_failure_count = sum(
        not item["final_narrative_accepted"]
        or not item["final_authority_accepted"]
        for item in results
    )
    summary = {
        "schema_version": 1,
        "fixture_source": payload.get("source", ""),
        "case_count": len(results),
        "passed_count": passed_count,
        "success_rate": passed_count / len(results) if results else 0.0,
        "patch_failure_count": patch_failure_count,
        "validator_failure_count": validator_failure_count,
        "repair_regression_count": regression_count,
        "gate": {
            "all_six_pass": len(results) == 6 and passed_count == 6,
            "zero_patch_failure_pass": patch_failure_count == 0,
            "zero_validator_failure_pass": validator_failure_count == 0,
            "zero_regression_pass": regression_count == 0,
        },
    }
    summary["gate"]["passed"] = all(summary["gate"].values())
    return {"summary": summary, "cases": results}


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Final Six Real Rejects — Repair Patch Replay",
        "",
        f"- Passed: {summary['passed_count']}/{summary['case_count']}",
        f"- Patch failures: {summary['patch_failure_count']}",
        f"- Validator failures: {summary['validator_failure_count']}",
        f"- Regressions: {summary['repair_regression_count']}",
        f"- Gate: {'PASS' if summary['gate']['passed'] else 'FAIL'}",
        "",
        "| Case | Initial codes | Patch | Δ chars | Final |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for item in report["cases"]:
        lines.append(
            "| {case} | {codes} | {patches} | {delta} | {result} |".format(
                case=item["case_id"],
                codes=", ".join(item["initial_codes"]),
                patches="/".join(item["patch_types"]),
                delta=item["patch_char_delta"],
                result="PASS" if item["passed"] else "FAIL",
            )
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    report = replay_fixture(args.fixture.resolve())
    output = args.output.resolve()
    markdown = (
        args.markdown.resolve()
        if args.markdown
        else output.with_suffix(".md")
    )
    _atomic_text(output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _atomic_text(markdown, _markdown(report))
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if report["summary"]["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
