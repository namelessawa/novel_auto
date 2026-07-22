from __future__ import annotations

import json
from pathlib import Path

import pytest

from story.models import StateDeltaOperation, StoryThread, WriterCandidate
from story.narrative_contract import RequiredEvent
from story.service import GenerationRejected
from story.writer import AuthorWriter
from tests.test_narrative_contract_generation import (
    ContractWriter,
    _candidate,
    _goal,
    _service,
)


@pytest.mark.asyncio
async def test_event_completion_repair_stores_deterministic_plan(
    tmp_path: Path,
) -> None:
    writer = ContractWriter(
        _candidate("沈砚准备交信给调查员，林秋仍拿着信。"),
        _candidate("沈砚把信交给调查员，调查员接过信并收进内袋。"),
    )
    service = _service(tmp_path, writer)

    transaction = await service.run(_goal(), request_id="event-plan-repair")

    assert transaction.committed is True
    assert transaction.event_execution_plan.ordered_events[0].id == "handover"
    assert transaction.repair_plan.incomplete_events[0].event_id == "handover"
    assert transaction.repair_plan.wrong_end_states[0].state_id == "holder"
    assert transaction.narrative_validation_history[-1].event_results[0].status == (
        "completed"
    )


@pytest.mark.asyncio
async def test_repair_cannot_alter_delta_or_threads_and_invalid_originals_drop(
    tmp_path: Path,
) -> None:
    original = _candidate("沈砚准备把信交给调查员，林秋仍拿着信。").model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set",
                    path="/story_bible/theme",
                    value="非法改写",
                    evidence="准备把信交给调查员",
                )
            ],
            "threads_advanced": [
                StoryThread(
                    id="unknown-thread",
                    description="不存在的线",
                    evidence=["准备把信交给调查员"],
                )
            ],
            "threads_opened": [
                StoryThread(
                    id="original-open",
                    description="交信之前的迟疑",
                    evidence=["准备把信交给调查员"],
                )
            ],
        }
    )
    malicious_repair = _candidate(
        "沈砚把信交给调查员，调查员接过信并收进内袋。"
    ).model_copy(
        update={
            "state_delta": [
                StateDeltaOperation(
                    op="set",
                    path="/world/weather",
                    value="暴雨",
                    evidence="不存在于正文的暴雨",
                )
            ],
            "threads_opened": [
                StoryThread(id="repair-added", description="Repair 新增故事线")
            ],
        }
    )
    service = _service(tmp_path, ContractWriter(original, malicious_repair))

    transaction = await service.run(_goal(), request_id="prose-only-repair")

    assert transaction.committed is True
    assert transaction.candidate.state_delta == []
    assert transaction.candidate.threads_opened == []
    assert transaction.candidate.threads_advanced == []
    assert transaction.validation_report.dropped_delta_count == 1
    assert transaction.validation_report.dropped_thread_change_count == 2
    assert "THREAD_OPEN_NO_EVIDENCE" in {
        item.code for item in transaction.validation_report.proposal_drops
    }
    assert service.states.load().world == {}
    assert service.threads.load().threads == {}


def test_author_writer_ignores_and_records_non_prose_repair_fields() -> None:
    original = _candidate("沈砚准备把信交给调查员。")
    content = json.dumps(
        {
            "narrative_text": "沈砚把信交给调查员，调查员接过信。",
            "state_delta": [{"op": "set"}],
            "threads_opened": [{"id": "bad"}],
            "title": "不应接受",
        },
        ensure_ascii=False,
    )

    repaired = AuthorWriter._parse_repair(content, original)

    assert repaired.narrative_text.startswith("沈砚把信交给")
    assert repaired.state_delta == original.state_delta
    assert repaired.title == original.title
    assert AuthorWriter._repair_ignored_fields(content) == [
        "state_delta",
        "threads_opened",
        "title",
    ]


@pytest.mark.asyncio
async def test_repair_regression_rejects_transaction(tmp_path: Path) -> None:
    goal = _goal()
    constraints = goal.narrative_constraints.model_copy(
        update={
            "required_events": [
                RequiredEvent(
                    id="bandage",
                    actor="shen",
                    action="包扎林秋的手",
                    target="lin",
                    evidence_patterns=[r"沈砚.{0,20}包扎.{0,20}林秋"],
                ),
                *goal.narrative_constraints.required_events,
            ]
        }
    )
    goal = goal.model_copy(update={"narrative_constraints": constraints})
    original = WriterCandidate(
        narrative_text="沈砚包扎了林秋的手。随后沈砚准备交信给调查员。",
        title="修复前",
        section_summary="已包扎，交信未完成。",
    )
    regressed = WriterCandidate(
        narrative_text="沈砚把信交给调查员，调查员接过信并收进内袋。",
        title="恶化",
        section_summary="交信完成。",
    )
    service = _service(tmp_path, ContractWriter(original, regressed))

    with pytest.raises(GenerationRejected) as exc:
        await service.run(goal, request_id="repair-regression")

    codes = [
        item.code
        for item in exc.value.transaction.narrative_validation_report.violations
    ]
    assert "REPAIR_REGRESSION" in codes
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_repair_enforcement_removes_replacement_unsupported_action(
    tmp_path: Path,
) -> None:
    original = _candidate(
        "沈砚反手扣住林秋，随后准备把信交给调查员，林秋仍拿着信。"
    )
    repaired = _candidate(
        "沈砚猛地甩开林秋的手，沈砚随后把信交给调查员，"
        "调查员接过信并收进内袋。"
    )
    service = _service(tmp_path, ContractWriter(original, repaired))

    transaction = await service.run(_goal(), request_id="repair-enforcement")

    assert transaction.committed is True
    assert "甩开" not in transaction.candidate.narrative_text
    assert transaction.repair_enforced_removals == [
        {"code": "UNSUPPORTED_INJURY_ADDED", "evidence": "甩开林秋的手"}
    ]
    assert transaction.narrative_validation_report.accepted is True
    assert transaction.narrative_validation_report.event_results[0].status == (
        "completed"
    )
