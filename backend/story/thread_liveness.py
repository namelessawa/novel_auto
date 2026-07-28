"""Deterministic main-thread liveness policy for author mode."""

from __future__ import annotations

from story.models import (
    SectionGoal,
    StoryThread,
    StoryThreadRepository,
    ThreadLivenessRecord,
    ValidationReport,
    ValidationViolation,
)


class ThreadLivenessPolicy:
    """Require due active threads to advance at least once every three sections."""

    def __init__(self, *, max_quiet_revisions: int = 2) -> None:
        self.max_quiet_revisions = max(1, int(max_quiet_revisions))

    def bind_goal(
        self,
        goal: SectionGoal,
        threads: StoryThreadRepository,
        *,
        canonical_revision: int,
    ) -> SectionGoal:
        if goal.pause_thread_progress:
            return goal
        due = self.due_threads(threads, canonical_revision=canonical_revision)
        required = list(
            dict.fromkeys(
                [
                    *goal.liveness_required_threads,
                    *[thread.id for thread in due],
                ]
            )
        )
        targets = list(dict.fromkeys([*goal.target_threads, *required]))
        return goal.model_copy(
            update={
                "target_threads": targets,
                "liveness_required_threads": required,
            }
        )

    def due_threads(
        self,
        threads: StoryThreadRepository,
        *,
        canonical_revision: int,
    ) -> list[StoryThread]:
        due: list[StoryThread] = []
        next_revision = canonical_revision + 1
        for thread in threads.threads.values():
            if thread.status in {"resolved", "abandoned"}:
                continue
            if (
                thread.target_start_revision
                and next_revision < thread.target_start_revision
            ):
                continue
            if thread.pause_until_revision >= next_revision:
                continue
            progress_revision = max(
                thread.last_advanced_revision,
                thread.updated_at_revision,
                thread.opened_at_revision,
            )
            age = max(0, canonical_revision - progress_revision)
            deadline_due = bool(
                thread.target_end_revision
                and next_revision >= thread.target_end_revision
            )
            if deadline_due or age >= self.max_quiet_revisions:
                due.append(thread)
        return sorted(
            due,
            key=lambda item: (
                item.target_end_revision or 10**12,
                -item.urgency,
                item.id,
            ),
        )

    def validate(
        self,
        goal: SectionGoal,
        threads: StoryThreadRepository,
        report: ValidationReport,
        *,
        canonical_revision: int,
    ) -> ValidationReport:
        changes = {
            change.thread.id: change
            for change in report.thread_changes
            if change.action in {"advanced", "resolved"}
        }
        violations = list(report.violations)
        for thread_id in goal.liveness_required_threads:
            if thread_id in changes:
                continue
            violations.append(
                ValidationViolation(
                    code="THREAD_LIVENESS_MISSED",
                    message=f"故事线 {thread_id} 已到推进窗口但本节没有可验证推进",
                    severity="high",
                    path=f"/threads/{thread_id}",
                    repair_hint="在一次局部 Repair 中补正文证据与对应线程推进提案",
                )
            )
        if len(violations) == len(report.violations):
            return report
        return report.model_copy(
            update={
                "accepted": False,
                "severity": "high",
                "violations": violations,
                "repairable": True,
                "repair_context": {
                    **report.repair_context,
                    "liveness_required_threads": goal.liveness_required_threads,
                    "canonical_revision": canonical_revision,
                },
            }
        )

    def records(
        self,
        goal: SectionGoal,
        threads: StoryThreadRepository,
        report: ValidationReport,
        *,
        canonical_revision: int,
    ) -> list[ThreadLivenessRecord]:
        changes = {
            change.thread.id: change
            for change in report.thread_changes
            if change.action in {"advanced", "resolved"}
        }
        required = set(goal.liveness_required_threads)
        records: list[ThreadLivenessRecord] = []
        for thread in sorted(threads.threads.values(), key=lambda item: item.id):
            if thread.status in {"resolved", "abandoned"}:
                continue
            progress_revision = max(
                thread.last_advanced_revision,
                thread.updated_at_revision,
                thread.opened_at_revision,
            )
            change = changes.get(thread.id)
            action = change.action if change else "none"
            evidence = list(change.thread.evidence) if change else []
            if change and change.action == "resolved":
                evidence = list(change.thread.resolution_evidence)
            paused = bool(
                goal.pause_thread_progress
                or thread.pause_until_revision >= canonical_revision + 1
            )
            records.append(
                ThreadLivenessRecord(
                    thread_id=thread.id,
                    canonical_revision_before=canonical_revision,
                    age_since_progress=max(
                        0, canonical_revision - progress_revision
                    ),
                    target_end_revision=thread.target_end_revision,
                    due=thread.id in required,
                    paused=paused,
                    action=action,
                    evidence=evidence,
                    compliant=thread.id not in required or change is not None,
                )
            )
        return records


__all__ = ["ThreadLivenessPolicy"]
