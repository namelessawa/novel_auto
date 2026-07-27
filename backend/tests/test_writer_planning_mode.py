from __future__ import annotations

from pathlib import Path

import pytest

from story.chapter_plan import ChapterEvidence, ChapterPlanBuilder
from story.models import WriterCandidate
from story.service import AuthorGenerationService, GenerationRejected
from story.writer import AuthorWriter, PlannerResult, WriterResult
from tests.test_author_generation_service import _goal, _service, _valid_candidate


class PlanningWriter:
    def __init__(
        self,
        candidate: WriterCandidate,
        *,
        report_evidence: bool = True,
        invalid_plan: bool = False,
        fail_writer: bool = False,
    ) -> None:
        self.candidate = candidate
        self.report_evidence = report_evidence
        self.invalid_plan = invalid_plan
        self.fail_writer = fail_writer
        self.plan_calls = 0
        self.generate_calls = 0

    async def plan(self, context, goal):
        del goal
        self.plan_calls += 1
        plan = ChapterPlanBuilder().build(
            event_plan=context.event_execution_plan,
            budget_plan=context.section_budget_plan,
        )
        if self.invalid_plan:
            first = plan.segments[0].model_copy(
                update={"target_chars": plan.segments[0].target_chars + 1}
            )
            plan = plan.model_copy(update={"segments": [first, *plan.segments[1:]]})
        return PlannerResult(
            plan=plan,
            usage={
                "prompt_tokens": 6,
                "completion_tokens": 4,
                "total_tokens": 10,
            },
        )

    async def generate(self, context, goal):
        del goal
        self.generate_calls += 1
        if self.fail_writer:
            raise RuntimeError("writer failed")
        assert context.chapter_plan is not None
        evidence = []
        if self.report_evidence:
            evidence = [
                ChapterEvidence(
                    segment=item.order,
                    events_completed=item.events,
                )
                for item in context.chapter_plan.segments
            ]
        return WriterResult(
            candidate=self.candidate.model_copy(
                update={"chapter_evidence": evidence}
            ),
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        )

    async def repair(self, candidate, plan):
        raise AssertionError(f"unexpected repair: {candidate.title} / {plan}")


@pytest.mark.asyncio
async def test_plan_followed_and_length_respected(tmp_path: Path) -> None:
    writer = PlanningWriter(_valid_candidate())
    service = _service(tmp_path, writer)

    transaction = await service.run(_goal(), request_id="planned_pass")

    assert transaction.committed is True
    assert transaction.chapter_plan_success is True
    assert transaction.writer_plan_followed is True
    assert transaction.writer_first_pass_pass is True
    assert transaction.planner_calls == 1
    assert transaction.writer_calls == 1
    assert transaction.usage["planner_tokens"] == 10
    assert transaction.usage["total_tokens"] == 160
    assert transaction.final_length_report.accepted is True
    assert transaction.final_ending_report.accepted is True


@pytest.mark.asyncio
async def test_plan_ignored_is_recorded_but_prose_validator_remains_authoritative(
    tmp_path: Path,
) -> None:
    writer = PlanningWriter(_valid_candidate(), report_evidence=False)
    service = _service(tmp_path, writer)

    transaction = await service.run(_goal(), request_id="plan_ignored")

    assert transaction.committed is True
    assert transaction.writer_plan_followed is False
    assert transaction.writer_plan_follow_report.accepted is False
    assert "PLAN_EVIDENCE_SEGMENT_MISSING" in {
        item.code
        for item in transaction.writer_plan_follow_report.violations
    }


@pytest.mark.asyncio
async def test_plan_failure_cannot_generate_or_commit(tmp_path: Path) -> None:
    writer = PlanningWriter(_valid_candidate(), invalid_plan=True)
    service = _service(tmp_path, writer)

    with pytest.raises(GenerationRejected) as error:
        await service.run(_goal(), request_id="plan_invalid")

    assert error.value.transaction.error_code == "CHAPTER_PLAN_INVALID"
    assert writer.generate_calls == 0
    assert service.states.load().revision == 1
    assert service.threads.load().revision == 1
    assert service.memories.load().revision == 1
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_writer_failure_after_valid_plan_cannot_commit(tmp_path: Path) -> None:
    writer = PlanningWriter(_valid_candidate(), fail_writer=True)
    service = _service(tmp_path, writer)

    with pytest.raises(RuntimeError, match="writer failed"):
        await service.run(_goal(), request_id="writer_failed")

    transaction = service.transactions.load("writer_failed")
    assert transaction.phase == "failed"
    assert transaction.chapter_plan_success is True
    assert service.states.load().revision == 1
    assert service.threads.load().revision == 1
    assert service.memories.load().revision == 1
    assert service.sections.count() == 0


@pytest.mark.asyncio
async def test_planner_cannot_alter_state_thread_or_memory(tmp_path: Path) -> None:
    writer = PlanningWriter(_valid_candidate())
    service: AuthorGenerationService = _service(tmp_path, writer)
    prepared = service.prepare(_goal(), request_id="planner_read_only")
    before = (
        service.states.load(),
        service.threads.load(),
        service.memories.load(),
        prepared.transaction.journal_canonical_revision,
    )

    await service.plan(prepared)

    assert service.states.load() == before[0]
    assert service.threads.load() == before[1]
    assert service.memories.load() == before[2]
    assert (
        service.transactions.load("planner_read_only").journal_canonical_revision
        == before[3]
    )


def test_writer_directive_stops_after_resolution() -> None:
    writer = PlanningWriter(_valid_candidate())
    # The directive is exercised through the service in the async tests; this
    # assertion pins the explicit stop contract against prompt regressions.
    assert "After segment 4" in AuthorWriter.PLANNING_WRITER_PROMPT
    assert "Do not create plot to fill length" in AuthorWriter.PLANNING_WRITER_PROMPT
