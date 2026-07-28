from __future__ import annotations

from story.models import (
    SectionGoal,
    StoryThread,
    StoryThreadRepository,
    ThreadChange,
    ValidationReport,
)
from story.thread_liveness import ThreadLivenessPolicy
from story.validator import StoryValidator


def _thread() -> StoryThread:
    return StoryThread(
        id="main_letter",
        type="conflict",
        description="查清旧信缺页",
        status="open",
        urgency=9,
        advance_condition="确认旧信缺失的页码",
        target_start_revision=1,
        target_end_revision=8,
        opened_at_revision=1,
        updated_at_revision=1,
    )


def _repository() -> StoryThreadRepository:
    thread = _thread()
    return StoryThreadRepository(revision=1, threads={thread.id: thread})


def test_due_thread_is_bound_to_contract_goal_on_third_section() -> None:
    policy = ThreadLivenessPolicy()

    goal = policy.bind_goal(
        SectionGoal(objective="继续调查"),
        _repository(),
        canonical_revision=3,
    )

    assert goal.target_threads == ["main_letter"]
    assert goal.liveness_required_threads == ["main_letter"]


def test_opening_unrelated_branch_cannot_evade_due_main_thread() -> None:
    policy = ThreadLivenessPolicy()
    goal = policy.bind_goal(
        SectionGoal(objective="继续调查"),
        _repository(),
        canonical_revision=3,
    )
    unrelated = StoryThread(
        id="side_branch",
        description="无关支线",
        evidence=["出现无关支线"],
    )
    base = ValidationReport(
        accepted=True,
        thread_changes=[ThreadChange(action="opened", thread=unrelated)],
    )

    report = policy.validate(
        goal,
        _repository(),
        base,
        canonical_revision=3,
    )

    assert report.accepted is False
    assert [item.code for item in report.violations] == [
        "THREAD_LIVENESS_MISSED"
    ]


def test_matching_advance_is_compliant_and_updates_progress_revision() -> None:
    policy = ThreadLivenessPolicy()
    repository = _repository()
    goal = policy.bind_goal(
        SectionGoal(objective="继续调查"),
        repository,
        canonical_revision=3,
    )
    advanced = _thread().model_copy(
        update={
            "status": "advancing",
            "evidence": ["确认旧信缺失的页码"],
        }
    )
    base = ValidationReport(
        accepted=True,
        thread_changes=[ThreadChange(action="advanced", thread=advanced)],
    )

    report = policy.validate(
        goal,
        repository,
        base,
        canonical_revision=3,
    )
    records = policy.records(
        goal,
        repository,
        report,
        canonical_revision=3,
    )
    updated = StoryValidator().apply_thread_changes(
        repository,
        report.thread_changes,
        target_revision=4,
    )

    assert report.accepted is True
    assert records[0].compliant is True
    assert records[0].action == "advanced"
    assert updated.threads["main_letter"].last_advanced_revision == 4
