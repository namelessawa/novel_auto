"""Bridge durable whole-book attempts into the existing Author transaction chain."""

from __future__ import annotations

from sections.section_store import TickSection
from story.models import GenerationTransaction
from story.production_models import (
    ProductionContextSnapshot,
    non_whitespace_char_count,
)
from story.production_service import (
    SectionCommitPending,
    SectionRunRequest,
    SectionRunResult,
)
from story.service import (
    AuthorGenerationService,
    CommitPendingError,
    GenerationRejected,
    ProductionSnapshotMismatchError,
)


class ProductionAdapterInvariantError(RuntimeError):
    """A supposedly committed Author transaction violates production limits."""


class AuthorProductionSectionRunner:
    """Use :class:`AuthorGenerationService` as the production section runner.

    The adapter never publishes the transaction's candidate field.  A result
    obtains prose exclusively from the official ``TickSection`` written by the
    Author commit journal.
    """

    def __init__(self, author_service: AuthorGenerationService) -> None:
        self.author_service = author_service

    async def run_section(self, request: SectionRunRequest) -> SectionRunResult:
        snapshot = request.snapshot
        goal = request.goal.model_copy(
            update={
                "section_id": request.section_id,
                "production_chapter_ordinal": snapshot.chapter_outline.ordinal,
                "production_section_ordinal": snapshot.section_ordinal,
            }
        )
        try:
            transaction = await self.author_service.run(
                goal,
                request_id=request.transaction_id,
                production_context=snapshot,
            )
        except GenerationRejected as exc:
            transaction = exc.transaction
        except CommitPendingError as exc:
            raise SectionCommitPending(str(exc)) from exc

        self._assert_transaction_identity(transaction, request)
        if transaction.phase == "rejected":
            return self._rejected_result(transaction, request)
        if not transaction.committed or transaction.phase != "committed":
            return SectionRunResult(
                transaction_id=request.transaction_id,
                section_id=request.section_id,
                committed=False,
                error_code=transaction.error_code or "AUTHOR_NOT_COMMITTED",
            )

        self._assert_call_budget(transaction)
        section = self.author_service.sections.get_by_id(request.transaction_id)
        if section is None:
            raise ProductionAdapterInvariantError(
                "committed Author transaction has no official TickSection"
            )
        self._assert_committed_section(section, transaction, request)
        return SectionRunResult(
            transaction_id=request.transaction_id,
            section_id=request.section_id,
            committed=True,
            content=section.content,
            summary=str(section.editor_trace.get("section_summary", "")),
            char_count=section.word_count,
            canonical_revision_after=section.canonical_state_revision,
            story_bible_revision=section.story_bible_revision,
            validation_passed=True,
            repair_performed=transaction.repair_performed,
            provider=transaction.provider,
            provider_model=transaction.provider_model,
            provider_source=transaction.provider_source,
            provider_config_fingerprint=(
                transaction.provider_config_fingerprint
            ),
            provider_config_fingerprints=(
                transaction.provider_config_fingerprints
            ),
            prompt_tokens=self._usage(transaction, "prompt_tokens"),
            completion_tokens=self._usage(transaction, "completion_tokens"),
            latency_ms=self._usage(transaction, "latency_ms"),
        )

    @staticmethod
    def _same_snapshot(
        left: ProductionContextSnapshot | None,
        right: ProductionContextSnapshot,
    ) -> bool:
        return left is not None and left.model_dump(
            mode="json"
        ) == right.model_dump(mode="json")

    def _assert_transaction_identity(
        self,
        transaction: GenerationTransaction,
        request: SectionRunRequest,
    ) -> None:
        if transaction.id != request.transaction_id:
            raise ProductionAdapterInvariantError(
                "Author transaction ID differs from the production attempt"
            )
        if transaction.section_id != request.section_id:
            raise ProductionAdapterInvariantError(
                "Author section ID differs from the production attempt"
            )
        if not self._same_snapshot(transaction.production_context, request.snapshot):
            raise ProductionSnapshotMismatchError(
                "Author transaction did not freeze the exact production snapshot"
            )

    @staticmethod
    def _assert_call_budget(transaction: GenerationTransaction) -> None:
        if transaction.planner_calls != 0:
            raise ProductionAdapterInvariantError(
                "production sections cannot call a planner"
            )
        provider_repair_expected = bool(
            transaction.repair_performed
            and transaction.repair_plan is not None
            and any(
                template.provider_text_required
                for template in transaction.repair_plan.patch_templates
            )
        )
        expected_writer_calls = 1 + int(
            provider_repair_expected
            and transaction.structured_output_repair_count == 0
        )
        if transaction.writer_calls != expected_writer_calls:
            raise ProductionAdapterInvariantError(
                "production Writer calls must equal one initial call plus the "
                "frozen plan's targeted provider repair"
            )
        if transaction.structured_output_repair_count > 1:
            raise ProductionAdapterInvariantError(
                "production sections allow at most one format-only JSON repair"
            )
        if (
            transaction.writer_calls
            + transaction.structured_output_repair_count
            > 2
        ):
            raise ProductionAdapterInvariantError(
                "production sections allow at most two Provider calls"
            )
        if transaction.writer_retry_count != 0 or transaction.writer_retry_performed:
            raise ProductionAdapterInvariantError(
                "production sections cannot perform a full Writer retry"
            )
        if len(transaction.candidate_history) > 1 + int(
            transaction.repair_performed
        ):
            raise ProductionAdapterInvariantError(
                "production transaction contains more than one repair candidate"
            )
        if len(transaction.narrative_validation_history) > 2:
            raise ProductionAdapterInvariantError(
                "production transaction contains more than one repair validation"
            )

    @staticmethod
    def _assert_committed_section(
        section: TickSection,
        transaction: GenerationTransaction,
        request: SectionRunRequest,
    ) -> None:
        snapshot = request.snapshot
        if section.id != request.section_id:
            raise ProductionAdapterInvariantError(
                "official TickSection ID differs from the production request"
            )
        if section.transaction_id != request.transaction_id:
            raise ProductionAdapterInvariantError(
                "official TickSection transaction ID differs from the request"
            )
        if section.generation_mode != "author":
            raise ProductionAdapterInvariantError(
                "production result must come from Author generation mode"
            )
        if (
            section.chapter != snapshot.chapter_outline.ordinal
            or section.section != snapshot.section_ordinal
        ):
            raise ProductionAdapterInvariantError(
                "official TickSection position differs from the frozen outline"
            )
        if section.story_bible_revision != snapshot.story_bible_revision:
            raise ProductionSnapshotMismatchError(
                "official TickSection used a different StoryBible revision"
            )
        expected_canonical = snapshot.canonical_state_revision + 1
        if (
            section.canonical_state_revision != expected_canonical
            or transaction.target_canonical_revision != expected_canonical
        ):
            raise ProductionSnapshotMismatchError(
                "official TickSection broke the frozen CanonicalState revision chain"
            )
        if section.word_count != non_whitespace_char_count(section.content):
            raise ProductionAdapterInvariantError(
                "official TickSection character count does not match its content"
            )
        if (
            transaction.narrative_validation_report is None
            or not transaction.narrative_validation_report.accepted
            or transaction.validation_report is None
            or not transaction.validation_report.accepted
            or not bool(section.validation_report.get("accepted"))
        ):
            raise ProductionAdapterInvariantError(
                "official TickSection lacks accepted validation evidence"
            )
        stored_goal = section.section_goal
        if (
            stored_goal.get("production_chapter_ordinal")
            != snapshot.chapter_outline.ordinal
            or stored_goal.get("production_section_ordinal")
            != snapshot.section_ordinal
        ):
            raise ProductionAdapterInvariantError(
                "official TickSection did not preserve its production position"
            )

    @staticmethod
    def _rejected_result(
        transaction: GenerationTransaction,
        request: SectionRunRequest,
    ) -> SectionRunResult:
        return SectionRunResult(
            transaction_id=request.transaction_id,
            section_id=request.section_id,
            committed=False,
            content="",
            char_count=0,
            validation_passed=False,
            repair_performed=transaction.repair_performed,
            provider=transaction.provider,
            provider_model=transaction.provider_model,
            provider_source=transaction.provider_source,
            provider_config_fingerprint=(
                transaction.provider_config_fingerprint
            ),
            provider_config_fingerprints=(
                transaction.provider_config_fingerprints
            ),
            prompt_tokens=AuthorProductionSectionRunner._usage(
                transaction, "prompt_tokens"
            ),
            completion_tokens=AuthorProductionSectionRunner._usage(
                transaction, "completion_tokens"
            ),
            latency_ms=AuthorProductionSectionRunner._usage(
                transaction, "latency_ms"
            ),
            error_code=transaction.error_code or "GENERATION_REJECTED",
        )

    @staticmethod
    def _usage(transaction: GenerationTransaction, key: str) -> int:
        return max(0, int(transaction.usage.get(key, 0)))


__all__ = [
    "AuthorProductionSectionRunner",
    "ProductionAdapterInvariantError",
]
