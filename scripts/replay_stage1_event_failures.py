"""Offline replay gate for the 24 frozen Stage 1 failure transactions."""

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

from story.event_execution import EventExecutionPlanBuilder  # noqa: E402
from story.models import (  # noqa: E402
    CanonicalState,
    SectionGoal,
    StoryBible,
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
    ROOT / "backend" / "tests" / "fixtures" / "stage1_event_repair_failures.json"
)
DEFAULT_OUTPUT = ROOT / ".tmp" / "event-completion-repair" / "offline-replay.json"


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".partial", dir=path.parent
    )
    partial = Path(raw)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(partial, path)
    finally:
        if partial.exists():
            partial.unlink()


def _state_from_contract(contract: NarrativeContract) -> CanonicalState:
    characters = {
        item.id: {
            "id": item.id,
            "name": item.name,
            "alive": True,
        }
        for item in contract.allowed_entities.characters
    }
    locations = {
        item.id: {"id": item.id, "name": item.name}
        for item in contract.allowed_entities.locations
    }
    items = {
        item.id: {
            "id": item.id,
            "name": item.name,
            "owners": [],
        }
        for item in contract.allowed_entities.items
    }
    return CanonicalState(
        revision=contract.canonical_state_revision,
        world={"locations": locations},
        characters=characters,
        items=items,
    )


def _bible_for_replay(contract: NarrativeContract, goal: SectionGoal) -> StoryBible:
    return StoryBible(
        revision=contract.story_bible_revision,
        premise=goal.objective,
        theme=goal.objective,
        setting_summary="Frozen Stage 1 replay",
    )


def replay_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    results: list[dict[str, Any]] = []
    narrative_validator = NarrativeContractValidator()
    authority_validator = StoryValidator()
    patch_validator = RepairPatchValidator()

    for case in cases:
        original_payload = case["original_candidate"]
        original_sha = hashlib.sha256(
            original_payload["narrative_text"].encode("utf-8")
        ).hexdigest()
        if original_sha != case["original_sha256"]:
            raise ValueError(f"fixture hash mismatch: {case['case_id']}")

        contract = NarrativeContract.model_validate(case["narrative_contract"])
        goal = SectionGoal.model_validate(case["section_goal"])
        original = WriterCandidate.model_validate(original_payload)
        state = _state_from_contract(contract)
        bible = _bible_for_replay(contract, goal)
        threads = StoryThreadRepository(revision=state.revision)
        event_plan = EventExecutionPlanBuilder().build(
            contract=contract,
            section_goal=goal,
            story_threads=[],
            canonical_state=state,
        )
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

        repair_plan = None
        patch_set = RepairPatchSet()
        patch_report = None
        repaired = not initial_narrative.accepted
        if repaired:
            repair_plan = RepairPlanBuilder().build(
                transaction_id=case["case_id"],
                contract=contract,
                event_plan=event_plan,
                narrative_report=initial_narrative,
                state_report=initial_authority,
                narrative_text=original.narrative_text,
            )
            patch_set = RepairPatchSet.model_validate(
                {
                    "patches": repair_patch_prompt_payload(
                        repair_plan,
                        original.narrative_text,
                    )["suggested_patch_templates"]
                }
            )
            patch_result = patch_validator.validate_and_apply(
                original_text=original.narrative_text,
                patch_set=patch_set,
                plan=repair_plan,
                contract=contract,
                event_plan=event_plan,
            )
            patch_report = patch_result.report
            final_text = patch_result.narrative_text
        else:
            final_text = original.narrative_text

        final_candidate = original.model_copy(update={"narrative_text": final_text})
        final_narrative = narrative_validator.validate(
            contract,
            final_text,
            event_execution_plan=event_plan,
            event_evidence=original.event_evidence,
            end_state_evidence=original.end_state_evidence,
        )
        regressions = (
            RepairRegressionValidator().validate(
                plan=repair_plan,
                final_report=final_narrative,
                repaired_text=final_text,
            )
            if repair_plan is not None
            else []
        )
        final_authority = authority_validator.validate(
            bible=bible,
            state=state,
            threads=threads,
            goal=goal,
            candidate=final_candidate,
            drop_unsupported_proposals=True,
        )
        recovered = (
            final_narrative.accepted
            and final_authority.accepted
            and not regressions
        )
        results.append(
            {
                "case_id": case["case_id"],
                "theme": case["theme"],
                "style": case["style"],
                "original_sha256": original_sha,
                "initial_contract_accepted": initial_narrative.accepted,
                "repair_attempted": repaired,
                "patch_accepted": (
                    patch_report.accepted if patch_report is not None else None
                ),
                "patch_count": len(patch_set.patches),
                "patch_types": [item.patch_type for item in patch_set.patches],
                "patch_codes": (
                    [item.code for item in patch_report.violations]
                    if patch_report is not None
                    else []
                ),
                "patch_char_delta": (
                    patch_report.char_delta if patch_report is not None else 0
                ),
                "repair_plan_counts": {
                    "missing_events": len(repair_plan.missing_events) if repair_plan else 0,
                    "incomplete_events": len(repair_plan.incomplete_events) if repair_plan else 0,
                    "wrong_actor_events": len(repair_plan.wrong_actor_events) if repair_plan else 0,
                    "wrong_target_events": len(repair_plan.wrong_target_events) if repair_plan else 0,
                    "wrong_end_states": len(repair_plan.wrong_end_states) if repair_plan else 0,
                },
                "final_contract_accepted": final_narrative.accepted,
                "final_contract_codes": [
                    item.code for item in final_narrative.violations
                ],
                "event_statuses": {
                    item.event_id: item.status for item in final_narrative.event_results
                },
                "repair_regression_count": len(regressions),
                "authority_accepted": final_authority.accepted,
                "authority_codes": [
                    item.code for item in final_authority.violations
                ],
                "dropped_delta_count": final_authority.dropped_delta_count,
                "dropped_thread_change_count": (
                    final_authority.dropped_thread_change_count
                ),
                "validated_delta_count": len(final_authority.validated_delta),
                "validated_thread_change_count": len(final_authority.thread_changes),
                "recovered": recovered,
            }
        )

    repaired_results = [item for item in results if item["repair_attempted"]]
    recovered_count = sum(item["recovered"] for item in results)
    repair_success_count = sum(item["recovered"] for item in repaired_results)
    regression_count = sum(item["repair_regression_count"] for item in results)
    bad_commit_count = sum(
        not item["authority_accepted"] or not item["final_contract_accepted"]
        for item in results
    )
    summary = {
        "schema_version": 1,
        "fixture_source": payload.get("source", ""),
        "case_count": len(results),
        "recovered_count": recovered_count,
        "recovery_rate": recovered_count / len(results) if results else 0.0,
        "repair_attempt_count": len(repaired_results),
        "repair_success_count": repair_success_count,
        "repair_success_rate": (
            repair_success_count / len(repaired_results) if repaired_results else 1.0
        ),
        "repair_regression_count": regression_count,
        "bad_commit_count": bad_commit_count,
        "dropped_delta_count": sum(item["dropped_delta_count"] for item in results),
        "dropped_thread_change_count": sum(
            item["dropped_thread_change_count"] for item in results
        ),
        "gate": {
            "required_recovered": len(results),
            "recovered_pass": recovered_count == len(results),
            "zero_regression_pass": regression_count == 0,
            "zero_bad_commit_pass": bad_commit_count == 0,
        },
    }
    summary["gate"]["passed"] = all(
        value for key, value in summary["gate"].items() if key.endswith("_pass")
    )
    return {"summary": summary, "cases": results}


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Stage 1 Repair Patch Offline Replay",
        "",
        f"- Cases: {summary['case_count']}",
        f"- Recovered: {summary['recovered_count']}/{summary['case_count']}",
        f"- Repair success: {summary['repair_success_count']}/{summary['repair_attempt_count']}",
        f"- Repair regressions: {summary['repair_regression_count']}",
        f"- Bad commits: {summary['bad_commit_count']}",
        f"- Dropped deltas: {summary['dropped_delta_count']}",
        f"- Dropped thread changes: {summary['dropped_thread_change_count']}",
        f"- Gate: {'PASS' if summary['gate']['passed'] else 'FAIL'}",
        "",
        "| Case | Repair | Patches | Contract | Authority | Delta drops | Thread drops | Result |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["cases"]:
        lines.append(
            "| {case_id} | {repair} | {patches} | {contract} | {authority} | {delta} | "
            "{thread} | {result} |".format(
                case_id=item["case_id"],
                repair="yes" if item["repair_attempted"] else "no",
                patches=item["patch_count"],
                contract="pass" if item["final_contract_accepted"] else "fail",
                authority="pass" if item["authority_accepted"] else "fail",
                delta=item["dropped_delta_count"],
                thread=item["dropped_thread_change_count"],
                result="PASS" if item["recovered"] else "FAIL",
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
