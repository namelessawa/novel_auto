"""Deterministic canonical revision checks for commit and recovery."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from story.narrative_contract import NarrativeModel


RevisionGuardMode = Literal["commit", "recovery"]


class RevisionGuardReport(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    mode: RevisionGuardMode
    accepted: bool
    expected_revision: int = Field(ge=1)
    journal_revision: int = Field(ge=1)
    current_revision: int = Field(ge=1)
    target_revision: int = Field(ge=1)
    error_code: str = ""


class RevisionGuardError(RuntimeError):
    def __init__(self, report: RevisionGuardReport) -> None:
        super().__init__(
            "REVISION_CHAIN_BROKEN: expected "
            f"{report.expected_revision}, journal {report.journal_revision}, "
            f"current {report.current_revision}, target {report.target_revision}"
        )
        self.report = report


class TransactionRevisionGuard:
    """Reject stale commits and ambiguous crash recovery."""

    @staticmethod
    def _values(transaction: Any) -> tuple[int, int, int]:
        expected = int(transaction.canonical_state_revision)
        journal = int(transaction.journal_canonical_revision)
        target = int(transaction.target_canonical_revision)
        return expected, journal, target

    def ensure_commit(
        self,
        transaction: Any,
        *,
        current_revision: int,
    ) -> RevisionGuardReport:
        expected, journal, target = self._values(transaction)
        accepted = (
            current_revision == expected
            and journal == expected
            and target == expected + 1
        )
        report = RevisionGuardReport(
            mode="commit",
            accepted=accepted,
            expected_revision=expected,
            journal_revision=journal,
            current_revision=current_revision,
            target_revision=target,
            error_code="" if accepted else "REVISION_CHAIN_BROKEN",
        )
        if not accepted:
            raise RevisionGuardError(report)
        return report

    def ensure_recovery(
        self,
        transaction: Any,
        *,
        current_revision: int,
    ) -> RevisionGuardReport:
        expected, journal, target = self._values(transaction)
        accepted = (
            journal == current_revision
            and current_revision in {expected, target}
            and target == expected + 1
        )
        report = RevisionGuardReport(
            mode="recovery",
            accepted=accepted,
            expected_revision=expected,
            journal_revision=journal,
            current_revision=current_revision,
            target_revision=target,
            error_code="" if accepted else "REVISION_CHAIN_BROKEN",
        )
        if not accepted:
            raise RevisionGuardError(report)
        return report


__all__ = [
    "RevisionGuardError",
    "RevisionGuardMode",
    "RevisionGuardReport",
    "TransactionRevisionGuard",
]
