"""AuthorGenerationService: prepare → generate → validate → repair → commit."""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import uuid
from dataclasses import dataclass

import novel_manager
from sections.section_store import TickSection, get_section_store
from story.context_builder import ContextBudgetExceeded, ContextBuilder, ContextPackage
from story.event_execution import (
    EventExecutionPlan,
    EventExecutionPlanBuilder,
)
from story.ending_validator import (
    EndingCompletionReport,
    EndingCompletionValidator,
)
from story.migrations import ensure_story_domain
from story.models import (
    CanonicalState,
    GenerationTransaction,
    MemoryRecord,
    MemoryRepositoryState,
    SectionGoal,
    StoryBible,
    StoryThreadRepository,
    ValidationReport,
    WriterCandidate,
    utc_now,
)
from story.narrative_contract import (
    NarrativeContract,
    NarrativeContractBuilder,
    NarrativeValidationReport,
    NarrativeViolation,
)
from story.narrative_validator import NarrativeContractValidator
from story.persistence import (
    CanonicalStateStore,
    ContextManifestStore,
    GenerationTransactionStore,
    MemoryRepository,
    RevisionConflict,
    StoryBibleStore,
    StoryThreadStore,
)
from story.repair_patch import RepairPatchSet, RepairPatchValidator
from story.repair_plan import RepairPlan, RepairPlanBuilder, RepairRegressionValidator
from story.revision_guard import RevisionGuardError, TransactionRevisionGuard
from story.section_budget import SectionBudgetPlan, SectionBudgetPlanBuilder
from story.section_length_validator import (
    LengthValidationPhase,
    SectionBalanceReport,
    SectionBalanceValidator,
    SectionLengthReport,
    SectionLengthValidator,
)
from story.validator import StoryValidator
from story.writer import AuthorWriter, WriterProtocol, WriterResult
from story.writer_preflight import (
    WriterPreflightReport,
    WriterPreflightValidator,
)
from story.writing_plan import (
    SectionWritingPlan,
    SectionWritingPlanBuilder,
)

logger = logging.getLogger(__name__)


class GenerationRejected(RuntimeError):
    def __init__(self, transaction: GenerationTransaction) -> None:
        super().__init__("candidate rejected by NarrativeContract/StoryValidator")
        self.transaction = transaction


class CommitPendingError(RuntimeError):
    pass


class StaleStoryBibleError(RuntimeError):
    def __init__(self, transaction: GenerationTransaction) -> None:
        super().__init__(transaction.error or "StoryBible revision became stale")
        self.transaction = transaction


class RevisionChainBrokenError(RuntimeError):
    def __init__(self, transaction: GenerationTransaction) -> None:
        super().__init__(transaction.error or "Canonical revision chain is broken")
        self.transaction = transaction


@dataclass(frozen=True)
class PreparedGeneration:
    bible: StoryBible
    state: CanonicalState
    threads: StoryThreadRepository
    memories: MemoryRepositoryState
    goal: SectionGoal
    narrative_contract: NarrativeContract
    event_execution_plan: EventExecutionPlan
    section_writing_plan: SectionWritingPlan
    section_budget_plan: SectionBudgetPlan
    context: ContextPackage
    transaction: GenerationTransaction


class AuthorGenerationService:
    """One-writer, at-most-one-repair transactional section service."""

    def __init__(
        self,
        *,
        user_id: str,
        novel_id: str,
        data_dir: str,
        title: str = "",
        writer: WriterProtocol | None = None,
        validator: StoryValidator | None = None,
        narrative_validator: NarrativeContractValidator | None = None,
        contract_builder: NarrativeContractBuilder | None = None,
        event_plan_builder: EventExecutionPlanBuilder | None = None,
        writing_plan_builder: SectionWritingPlanBuilder | None = None,
        budget_plan_builder: SectionBudgetPlanBuilder | None = None,
        preflight_validator: WriterPreflightValidator | None = None,
        repair_plan_builder: RepairPlanBuilder | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.user_id = user_id
        self.novel_id = novel_id
        self.data_dir = os.path.realpath(os.path.abspath(data_dir))
        ensure_story_domain(self.data_dir, title=title)
        self.bibles = StoryBibleStore(self.data_dir)
        self.states = CanonicalStateStore(self.data_dir)
        self.threads = StoryThreadStore(self.data_dir)
        self.memories = MemoryRepository(self.data_dir)
        self.transactions = GenerationTransactionStore(self.data_dir)
        self.manifests = ContextManifestStore(self.data_dir, novel_id=novel_id)
        self.sections = get_section_store(novel_id, data_dir=self.data_dir)
        self.writer = writer or AuthorWriter()
        self.validator = validator or StoryValidator()
        self.narrative_validator = narrative_validator or NarrativeContractValidator()
        self.contract_builder = contract_builder or NarrativeContractBuilder()
        self.event_plan_builder = event_plan_builder or EventExecutionPlanBuilder()
        self.writing_plan_builder = writing_plan_builder or SectionWritingPlanBuilder()
        self.budget_plan_builder = budget_plan_builder or SectionBudgetPlanBuilder()
        self.section_length_validator = SectionLengthValidator()
        self.ending_completion_validator = EndingCompletionValidator()
        self.section_balance_validator = SectionBalanceValidator()
        self.writer_preflight_validator = (
            preflight_validator or WriterPreflightValidator()
        )
        self.repair_plan_builder = repair_plan_builder or RepairPlanBuilder()
        self.repair_regression_validator = RepairRegressionValidator()
        self.repair_patch_validator = RepairPatchValidator()
        self.context_builder = context_builder or ContextBuilder()
        self.revision_guard = TransactionRevisionGuard()
        self._generation_lock = asyncio.Lock()
        self.recover()

    async def run(
        self,
        goal: SectionGoal,
        *,
        request_id: str | None = None,
    ) -> GenerationTransaction:
        request_id = request_id or f"author_{uuid.uuid4().hex[:16]}"
        async with self._generation_lock:
            if self.transactions.exists(request_id):
                existing = self.transactions.load(request_id)
                if existing.committed or existing.phase == "rejected":
                    return existing
                if existing.phase == "stale_context":
                    raise StaleStoryBibleError(existing)
                if existing.phase in {"validated", "committing"}:
                    self._commit_staged(existing)
                    return self.transactions.load(request_id)
                raise CommitPendingError(
                    f"transaction {request_id} already exists in phase {existing.phase}"
                )

            prepared = self.prepare(goal, request_id=request_id)
            transaction = prepared.transaction
            try:
                generated = await self.generate(prepared)
                transaction = self._record_generated(transaction, generated)
                candidate = generated.candidate
                initial_preflight_report = self.preflight(prepared, candidate)
                transaction = transaction.model_copy(
                    update={
                        "initial_preflight_report": initial_preflight_report,
                        "final_preflight_report": initial_preflight_report,
                        "updated_at": utc_now(),
                    }
                )
                self.transactions.save(transaction)
                retry_method = getattr(self.writer, "retry", None)
                if initial_preflight_report.retry_required and callable(retry_method):
                    retried = await self.retry(
                        prepared,
                        candidate,
                        initial_preflight_report,
                    )
                    candidate = retried.candidate
                    final_preflight_report = self.preflight(prepared, candidate)
                    transaction = transaction.model_copy(
                        update={
                            "candidate": candidate,
                            "candidate_history": [
                                *transaction.candidate_history,
                                candidate,
                            ],
                            "writer_calls": 2,
                            "writer_retry_count": 1,
                            "writer_retry_performed": True,
                            "final_preflight_report": final_preflight_report,
                            "usage": self._merge_usage(
                                transaction.usage,
                                retried.usage,
                                phase="retry",
                            ),
                            "updated_at": utc_now(),
                        }
                    )
                    self.transactions.save(transaction)
                (
                    narrative_report,
                    initial_length_report,
                    initial_ending_report,
                    initial_balance_report,
                ) = self._section_reports(
                    prepared,
                    candidate,
                    phase="initial",
                )
                strict_report = self.validate(prepared, candidate)
                report = strict_report
                writer_first_pass_pass = bool(
                    initial_preflight_report.accepted
                    and narrative_report.accepted
                    and strict_report.accepted
                )
                narrative_history = [narrative_report]
                validation_history = [strict_report]
                transaction = transaction.model_copy(
                    update={
                        "narrative_validation_report": narrative_report,
                        "narrative_validation_history": narrative_history,
                        "validation_report": report,
                        "validation_history": validation_history,
                        "style_validation_report": self._style_report(
                            prepared, candidate, narrative_report
                        ),
                        "writer_first_pass_pass": writer_first_pass_pass,
                        "initial_length_report": initial_length_report,
                        "final_length_report": initial_length_report.model_copy(
                            update={"phase": "final"}
                        ),
                        "initial_ending_report": initial_ending_report,
                        "final_ending_report": initial_ending_report.model_copy(
                            update={"phase": "final"}
                        ),
                        "initial_balance_report": initial_balance_report,
                        "final_balance_report": initial_balance_report.model_copy(
                            update={"phase": "final"}
                        ),
                        "updated_at": utc_now(),
                    }
                )
                self.transactions.save(transaction)

                # Repair returns only bounded local patches.  Invalid optional
                # delta/thread proposals are still dropped server-side and can
                # never be rewritten by the model.
                if narrative_report.violations and narrative_report.repairable:
                    repair_plan = self._repair_plan(
                        prepared,
                        transaction,
                        candidate,
                        narrative_report,
                        strict_report,
                        initial_ending_report,
                    )
                    transaction = transaction.model_copy(
                        update={"repair_plan": repair_plan, "updated_at": utc_now()}
                    )
                    self.transactions.save(transaction)
                    original_candidate = candidate
                    repaired = await self.repair(candidate, repair_plan)
                    patch_set = repaired.repair_patches or RepairPatchSet()
                    patch_result = self.repair_patch_validator.validate_and_apply(
                        original_text=original_candidate.narrative_text,
                        patch_set=patch_set,
                        plan=repair_plan,
                        contract=prepared.narrative_contract,
                        event_plan=prepared.event_execution_plan,
                    )
                    if patch_result.report.accepted:
                        candidate = original_candidate.model_copy(
                            update={"narrative_text": patch_result.narrative_text}
                        )
                        candidate_history = [
                            *transaction.candidate_history,
                            candidate,
                        ]
                    else:
                        candidate = original_candidate
                        candidate_history = list(transaction.candidate_history)
                    patch_codes = [
                        item.code for item in patch_result.report.violations
                    ]
                    transaction = transaction.model_copy(
                        update={
                            "candidate": candidate,
                            "candidate_history": candidate_history,
                            "writer_calls": min(3, transaction.writer_calls + 1),
                            "repair_performed": True,
                            "repair_patches": patch_set,
                            "repair_patch_report": patch_result.report,
                            "repair_ignored_fields": repaired.ignored_fields,
                            "repair_audit_codes": list(
                                dict.fromkeys(
                                    [*repaired.audit_codes, *patch_codes]
                                )
                            ),
                            "usage": self._merge_usage(
                                transaction.usage,
                                repaired.usage,
                                phase="repair",
                            ),
                            "updated_at": utc_now(),
                        }
                    )
                    self.transactions.save(transaction)
                    if patch_result.report.accepted:
                        (
                            narrative_report,
                            final_length_report,
                            final_ending_report,
                            final_balance_report,
                        ) = self._section_reports(
                            prepared,
                            candidate,
                            phase="repaired",
                        )
                        regressions = self.repair_regression_validator.validate(
                            plan=repair_plan,
                            final_report=narrative_report,
                            repaired_text=candidate.narrative_text,
                        )
                        if regressions:
                            narrative_report = narrative_report.model_copy(
                                update={
                                    "accepted": False,
                                    "severity": "high",
                                    "violations": [
                                        *narrative_report.violations,
                                        *regressions,
                                    ],
                                }
                            )
                    else:
                        patch_violations = [
                            NarrativeViolation(
                                code=item.code,
                                message=item.message,
                                severity="high",
                                evidence=item.evidence,
                                repair_hint=(
                                    "局部 Patch 无效；事务拒绝且不允许第二次 Repair"
                                ),
                            )
                            for item in patch_result.report.violations
                        ]
                        narrative_report = narrative_report.model_copy(
                            update={
                                "accepted": False,
                                "severity": "high",
                                "violations": [
                                    *narrative_report.violations,
                                    *patch_violations,
                                ],
                            }
                        )
                        final_length_report = self.section_length_validator.validate(
                            candidate.narrative_text,
                            prepared.section_budget_plan,
                            phase="repaired",
                        )
                        final_ending_report = (
                            self.ending_completion_validator.validate(
                                narrative_text=candidate.narrative_text,
                                contract=prepared.narrative_contract,
                                narrative_report=narrative_report,
                                phase="repaired",
                            )
                        )
                        final_balance_report = self.section_balance_validator.validate(
                            narrative_report=narrative_report,
                            length_report=final_length_report,
                            ending_report=final_ending_report,
                            phase="repaired",
                        )
                    report = self.validate(
                        prepared,
                        candidate,
                        drop_unsupported_proposals=True,
                    )
                    transaction = transaction.model_copy(
                        update={
                            "final_length_report": final_length_report,
                            "final_ending_report": final_ending_report,
                            "final_balance_report": final_balance_report,
                            "updated_at": utc_now(),
                        }
                    )
                    self.transactions.save(transaction)
                    narrative_history.append(narrative_report)
                    validation_history.append(report)
                else:
                    report = self.validate(
                        prepared,
                        candidate,
                        drop_unsupported_proposals=True,
                    )
                    if report.model_dump(mode="json") != strict_report.model_dump(
                        mode="json"
                    ):
                        validation_history.append(report)

                if not narrative_report.accepted or not report.accepted:
                    rejected = transaction.model_copy(
                        update={
                            "phase": "rejected",
                            "candidate": candidate,
                            "narrative_validation_report": narrative_report,
                            "narrative_validation_history": narrative_history,
                            "validation_report": report,
                            "validation_history": validation_history,
                            "style_validation_report": self._style_report(
                                prepared, candidate, narrative_report
                            ),
                            "error": "正文或权威状态契约在一次修复后仍未通过",
                            "updated_at": utc_now(),
                        }
                    )
                    self.transactions.save(rejected)
                    raise GenerationRejected(rejected)

                transaction = transaction.model_copy(
                    update={
                        "narrative_validation_report": narrative_report,
                        "narrative_validation_history": narrative_history,
                        "validation_report": report,
                        "validation_history": validation_history,
                        "style_validation_report": self._style_report(
                            prepared, candidate, narrative_report
                        ),
                    }
                )
                staged = self._stage(prepared, transaction, candidate, report)
                self.commit(staged)
                novel_manager.touch_last_accessed(self.user_id, self.novel_id)
                return self.transactions.load(staged.id)
            except GenerationRejected:
                raise
            except StaleStoryBibleError:
                raise
            except RevisionChainBrokenError:
                raise
            except Exception as exc:
                # A committing transaction is intentionally left recoverable.
                current = self.transactions.load(transaction.id)
                if current.phase == "committing":
                    raise CommitPendingError(
                        f"transaction {current.id} will be recovered on restart: {exc}"
                    ) from exc
                failed = current.model_copy(
                    update={
                        "phase": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                        "updated_at": utc_now(),
                    }
                )
                self.transactions.save(failed)
                raise

    async def submit_candidate(
        self,
        goal: SectionGoal,
        candidate: WriterCandidate,
        *,
        request_id: str,
        generation_mode: str,
    ) -> GenerationTransaction:
        """Validate and commit an externally produced candidate.

        Simulation agents use this gateway instead of writing CanonicalState or
        official sections directly.  They already paid for their own generation
        and critique, so this path performs no additional Writer/repair call.
        A rejected candidate is journaled for audit and produces no official state.
        """
        if generation_mode not in {"author", "simulation"}:
            raise ValueError(f"unsupported generation mode: {generation_mode}")
        async with self._generation_lock:
            if self.transactions.exists(request_id):
                existing = self.transactions.load(request_id)
                if existing.committed or existing.phase == "rejected":
                    return existing
                if existing.phase == "stale_context":
                    raise StaleStoryBibleError(existing)
                if existing.phase in {"validated", "committing"}:
                    self._commit_staged(existing)
                    return self.transactions.load(request_id)
                raise CommitPendingError(
                    f"transaction {request_id} already exists in phase {existing.phase}"
                )

            prepared = self.prepare(
                goal,
                request_id=request_id,
                require_default_objective_event=(generation_mode == "author"),
            )
            transaction = prepared.transaction.model_copy(
                update={
                    "phase": "generated",
                    "candidate": candidate,
                    "writer_calls": 0,
                    "updated_at": utc_now(),
                }
            )
            self.transactions.save(transaction)
            (
                narrative_report,
                length_report,
                ending_report,
                balance_report,
            ) = self._section_reports(
                prepared,
                candidate,
                phase="final",
                enforce_writing_length=(generation_mode == "author"),
            )
            report = self.validate(
                prepared,
                candidate,
                source_mode=generation_mode,
            )
            if not narrative_report.accepted or not report.accepted:
                rejected = transaction.model_copy(
                    update={
                        "phase": "rejected",
                        "narrative_validation_report": narrative_report,
                        "narrative_validation_history": [narrative_report],
                        "validation_report": report,
                        "validation_history": [report],
                        "style_validation_report": self._style_report(
                            prepared, candidate, narrative_report
                        ),
                        "initial_length_report": length_report.model_copy(
                            update={"phase": "initial"}
                        ),
                        "final_length_report": length_report,
                        "initial_ending_report": ending_report.model_copy(
                            update={"phase": "initial"}
                        ),
                        "final_ending_report": ending_report,
                        "initial_balance_report": balance_report.model_copy(
                            update={"phase": "initial"}
                        ),
                        "final_balance_report": balance_report,
                        "error": "外部候选未通过正文或权威状态契约校验",
                        "updated_at": utc_now(),
                    }
                )
                return self.transactions.save(rejected)

            staged = self._stage(
                prepared,
                transaction.model_copy(
                    update={
                        "narrative_validation_report": narrative_report,
                        "narrative_validation_history": [narrative_report],
                        "validation_report": report,
                        "validation_history": [report],
                        "style_validation_report": self._style_report(
                            prepared, candidate, narrative_report
                        ),
                        "initial_length_report": length_report.model_copy(
                            update={"phase": "initial"}
                        ),
                        "final_length_report": length_report,
                        "initial_ending_report": ending_report.model_copy(
                            update={"phase": "initial"}
                        ),
                        "final_ending_report": ending_report,
                        "initial_balance_report": balance_report.model_copy(
                            update={"phase": "initial"}
                        ),
                        "final_balance_report": balance_report,
                    }
                ),
                candidate,
                report,
                generation_mode=generation_mode,
            )
            self.commit(staged)
            novel_manager.touch_last_accessed(self.user_id, self.novel_id)
            return self.transactions.load(staged.id)

    def prepare(
        self,
        goal: SectionGoal,
        *,
        request_id: str,
        require_default_objective_event: bool = True,
    ) -> PreparedGeneration:
        bible = self.bibles.load()
        publish_errors = bible.publish_errors()
        if publish_errors:
            raise ValueError("StoryBible 尚不可用于生成: " + "；".join(publish_errors))
        state = self.states.load()
        threads = self.threads.load()
        memories = self.memories.load()
        chapter, section = self.sections.next_position()
        section_id = goal.section_id or f"ch{chapter:04d}_s{section:04d}"
        prepared_goal = goal.model_copy(update={"section_id": section_id})

        previous = self.sections.get_last()
        previous_tail = previous.content[-5000:] if previous else ""
        recent_summaries = [
            {
                "section_id": item.id or f"ch{item.chapter}_s{item.section}",
                "summary": item.editor_trace.get("section_summary", ""),
            }
            for item in self.sections.list_all()[-12:]
            if item.editor_trace.get("section_summary")
        ]
        entity_ids = set(prepared_goal.involved_characters)
        if prepared_goal.viewpoint_character_id:
            entity_ids.add(prepared_goal.viewpoint_character_id)
        long_memories = self.memories.relevant(
            entity_ids,
            set(prepared_goal.target_threads),
            limit=12,
        )
        narrative_contract = self.contract_builder.build(
            story_bible=bible,
            canonical_state=state,
            section_goal=prepared_goal,
            story_threads=list(threads.threads.values()),
            require_default_objective_event=require_default_objective_event,
        )
        event_execution_plan = self.event_plan_builder.build(
            contract=narrative_contract,
            section_goal=prepared_goal,
            story_threads=list(threads.threads.values()),
            canonical_state=state,
            style_contract=bible.style_contract,
        )
        section_writing_plan = self.writing_plan_builder.build(
            contract=narrative_contract,
            event_plan=event_execution_plan,
            section_goal=prepared_goal,
            style_contract=bible.style_contract,
        )
        section_budget_plan = self.budget_plan_builder.build(
            writing_plan=section_writing_plan,
            style_contract=bible.style_contract,
        )
        try:
            context = self.context_builder.build(
                novel_id=self.novel_id,
                section_id=section_id,
                story_bible=bible,
                canonical_state=state,
                narrative_contract=narrative_contract,
                event_execution_plan=event_execution_plan,
                section_writing_plan=section_writing_plan,
                section_budget_plan=section_budget_plan,
                section_goal=prepared_goal,
                story_threads=list(threads.threads.values()),
                previous_prose_tail=previous_tail,
                recent_summaries=recent_summaries,
                long_term_memories=long_memories,
            )
        except ContextBudgetExceeded as exc:
            self.manifests.save(exc.manifest)
            raise
        self.manifests.save(context.manifest)
        transaction = GenerationTransaction(
            id=request_id,
            user_id=self.user_id,
            novel_id=self.novel_id,
            section_id=section_id,
            story_bible_revision=bible.revision,
            canonical_state_revision=state.revision,
            target_canonical_revision=state.revision + 1,
            journal_canonical_revision=state.revision,
            narrative_contract=narrative_contract,
            event_execution_plan=event_execution_plan,
            section_writing_plan=section_writing_plan,
            section_budget_plan=section_budget_plan,
            context_manifest=context.manifest,
        )
        self.transactions.save(transaction)
        return PreparedGeneration(
            bible=bible,
            state=state,
            threads=threads,
            memories=memories,
            goal=prepared_goal,
            narrative_contract=narrative_contract,
            event_execution_plan=event_execution_plan,
            section_writing_plan=section_writing_plan,
            section_budget_plan=section_budget_plan,
            context=context,
            transaction=transaction,
        )

    def preview_contract(self, goal: SectionGoal) -> NarrativeContract:
        """Read-only contract preview; does not create a transaction or manifest."""
        bible = self.bibles.load()
        publish_errors = bible.publish_errors()
        if publish_errors:
            raise ValueError("StoryBible 尚不可用于生成: " + "；".join(publish_errors))
        state = self.states.load()
        threads = self.threads.load()
        chapter, section = self.sections.next_position()
        section_id = goal.section_id or f"ch{chapter:04d}_s{section:04d}"
        prepared_goal = goal.model_copy(update={"section_id": section_id})
        return self.contract_builder.build(
            story_bible=bible,
            canonical_state=state,
            section_goal=prepared_goal,
            story_threads=list(threads.threads.values()),
        )

    def preview_event_execution_plan(self, goal: SectionGoal) -> EventExecutionPlan:
        bible = self.bibles.load()
        state = self.states.load()
        threads = self.threads.load()
        chapter, section = self.sections.next_position()
        section_id = goal.section_id or f"ch{chapter:04d}_s{section:04d}"
        prepared_goal = goal.model_copy(update={"section_id": section_id})
        contract = self.contract_builder.build(
            story_bible=bible,
            canonical_state=state,
            section_goal=prepared_goal,
            story_threads=list(threads.threads.values()),
        )
        return self.event_plan_builder.build(
            contract=contract,
            section_goal=prepared_goal,
            story_threads=list(threads.threads.values()),
            canonical_state=state,
            style_contract=bible.style_contract,
        )

    def preview_section_writing_plan(self, goal: SectionGoal) -> SectionWritingPlan:
        bible = self.bibles.load()
        state = self.states.load()
        threads = self.threads.load()
        chapter, section = self.sections.next_position()
        section_id = goal.section_id or f"ch{chapter:04d}_s{section:04d}"
        prepared_goal = goal.model_copy(update={"section_id": section_id})
        contract = self.contract_builder.build(
            story_bible=bible,
            canonical_state=state,
            section_goal=prepared_goal,
            story_threads=list(threads.threads.values()),
        )
        event_plan = self.event_plan_builder.build(
            contract=contract,
            section_goal=prepared_goal,
            story_threads=list(threads.threads.values()),
            canonical_state=state,
            style_contract=bible.style_contract,
        )
        return self.writing_plan_builder.build(
            contract=contract,
            event_plan=event_plan,
            section_goal=prepared_goal,
            style_contract=bible.style_contract,
        )

    def preview_section_budget_plan(self, goal: SectionGoal) -> SectionBudgetPlan:
        bible = self.bibles.load()
        writing_plan = self.preview_section_writing_plan(goal)
        return self.budget_plan_builder.build(
            writing_plan=writing_plan,
            style_contract=bible.style_contract,
        )

    async def generate(self, prepared: PreparedGeneration) -> WriterResult:
        return await self.writer.generate(prepared.context, prepared.goal)

    def preflight(
        self,
        prepared: PreparedGeneration,
        candidate: WriterCandidate,
    ) -> WriterPreflightReport:
        return self.writer_preflight_validator.validate(
            candidate=candidate,
            contract=prepared.narrative_contract,
            event_plan=prepared.event_execution_plan,
            budget_plan=prepared.section_budget_plan,
        )

    async def retry(
        self,
        prepared: PreparedGeneration,
        candidate: WriterCandidate,
        preflight_report: WriterPreflightReport,
    ) -> WriterResult:
        retry_method = getattr(self.writer, "retry", None)
        if not callable(retry_method):
            raise RuntimeError("configured Writer does not support Writer Retry")
        return await retry_method(
            prepared.context,
            prepared.goal,
            candidate,
            preflight_report,
        )

    def validate(
        self,
        prepared: PreparedGeneration,
        candidate: WriterCandidate,
        *,
        source_mode: str = "author",
        drop_unsupported_proposals: bool = False,
    ) -> ValidationReport:
        return self.validator.validate(
            bible=prepared.bible,
            state=prepared.state,
            threads=prepared.threads,
            goal=prepared.goal,
            candidate=candidate,
            source_mode=source_mode,
            drop_unsupported_proposals=drop_unsupported_proposals,
        )

    def validate_narrative(
        self,
        prepared: PreparedGeneration,
        candidate: WriterCandidate,
        *,
        enforce_writing_length: bool = True,
    ) -> NarrativeValidationReport:
        return self._section_reports(
            prepared,
            candidate,
            phase="final",
            enforce_writing_length=enforce_writing_length,
        )[0]

    def _section_reports(
        self,
        prepared: PreparedGeneration,
        candidate: WriterCandidate,
        *,
        phase: LengthValidationPhase,
        enforce_writing_length: bool = True,
    ) -> tuple[
        NarrativeValidationReport,
        SectionLengthReport,
        EndingCompletionReport,
        SectionBalanceReport,
    ]:
        base_report = self.narrative_validator.validate(
            prepared.narrative_contract,
            candidate.narrative_text,
            event_execution_plan=prepared.event_execution_plan,
            event_evidence=candidate.event_evidence,
            end_state_evidence=candidate.end_state_evidence,
        )
        length_report = self.section_length_validator.validate(
            candidate.narrative_text,
            prepared.section_budget_plan,
            phase=phase,
        )
        ending_report = self.ending_completion_validator.validate(
            narrative_text=candidate.narrative_text,
            contract=prepared.narrative_contract,
            narrative_report=base_report,
            phase=phase,
        )
        report = base_report
        if enforce_writing_length:
            additions = [
                item
                for item in (
                    self.section_length_validator.violation(length_report),
                    self.ending_completion_validator.violation(ending_report),
                )
                if item is not None
            ]
            if additions:
                replaced_codes = {
                    "NARRATIVE_TOO_SHORT",
                    "NARRATIVE_TOO_LONG",
                    "POST_RESOLUTION_EXPANSION",
                }
                violations = [
                    item
                    for item in base_report.violations
                    if item.code not in replaced_codes
                ]
                report = base_report.model_copy(
                    update={
                        "accepted": False,
                        "severity": "high",
                        "violations": [*violations, *additions],
                        "repairable": True,
                    }
                )
        balance_report = self.section_balance_validator.validate(
            narrative_report=report,
            length_report=length_report,
            ending_report=ending_report,
            phase=phase,
        )
        return report, length_report, ending_report, balance_report

    async def repair(
        self,
        candidate: WriterCandidate,
        plan: RepairPlan,
    ) -> WriterResult:
        return await self.writer.repair(candidate, plan)

    def _repair_plan(
        self,
        prepared: PreparedGeneration,
        transaction: GenerationTransaction,
        candidate: WriterCandidate,
        narrative_report: NarrativeValidationReport,
        state_report: ValidationReport,
        ending_report: EndingCompletionReport,
    ) -> RepairPlan:
        return self.repair_plan_builder.build(
            transaction_id=transaction.id,
            contract=prepared.narrative_contract,
            event_plan=prepared.event_execution_plan,
            narrative_report=narrative_report,
            state_report=state_report,
            narrative_text=candidate.narrative_text,
            section_writing_plan=prepared.section_writing_plan,
            ending_report=ending_report,
        )

    @staticmethod
    def _style_report(
        prepared: PreparedGeneration,
        candidate: WriterCandidate,
        narrative_report: NarrativeValidationReport,
    ) -> dict:
        snapshot = prepared.bible.style_contract or {}
        style_key = str(snapshot.get("key") or "")
        if not style_key:
            return {
                "evaluated": False,
                "reason": "StoryBible has no StylePreset key",
                "eligible_for_overall_acceptance": narrative_report.accepted,
            }
        try:
            from novel_presets.style_presets import get_style_preset
            from quality_metrics.style_contract import style_contract_report

            preset = get_style_preset(style_key)
            rules = tuple(snapshot.get("det_rules") or preset.det_rules)
            payload = style_contract_report(
                style_key,
                candidate.narrative_text,
                rules,
                strict=True,
            ).to_dict()
            payload.update(
                {
                    "evaluated": True,
                    "evaluated_after_narrative": True,
                    "eligible_for_overall_acceptance": narrative_report.accepted,
                }
            )
            return payload
        except Exception as exc:
            return {
                "evaluated": False,
                "reason": type(exc).__name__,
                "eligible_for_overall_acceptance": narrative_report.accepted,
            }

    def commit(self, transaction: GenerationTransaction) -> None:
        self._commit_staged(transaction)

    def recover(self) -> list[str]:
        recovered: list[str] = []
        for transaction in self.transactions.list_pending():
            try:
                self._commit_staged(transaction)
                committed = self.transactions.load(transaction.id)
                self.transactions.save(
                    committed.model_copy(
                        update={"recovery_count": committed.recovery_count + 1}
                    )
                )
                recovered.append(transaction.id)
            except Exception as exc:
                logger.error("author transaction recovery failed %s: %s", transaction.id, exc)
        return recovered

    def _record_generated(
        self,
        transaction: GenerationTransaction,
        result: WriterResult,
    ) -> GenerationTransaction:
        generated = transaction.model_copy(
            update={
                "phase": "generated",
                "candidate": result.candidate,
                "candidate_history": [result.candidate],
                "writer_calls": 1,
                "usage": result.usage,
                "updated_at": utc_now(),
            }
        )
        return self.transactions.save(generated)

    def _stage(
        self,
        prepared: PreparedGeneration,
        transaction: GenerationTransaction,
        candidate: WriterCandidate,
        report: ValidationReport,
        *,
        generation_mode: str = "author",
    ) -> GenerationTransaction:
        (
            narrative_report,
            final_length_report,
            final_ending_report,
            final_balance_report,
        ) = self._section_reports(
            prepared,
            candidate,
            phase="final",
            enforce_writing_length=(generation_mode == "author"),
        )
        authority_report = self.validate(
            prepared,
            candidate,
            source_mode=generation_mode,
            drop_unsupported_proposals=True,
        )
        if not narrative_report.accepted or not authority_report.accepted:
            raise ValueError("cannot stage a failed narrative or authority contract")
        report = authority_report
        candidate = self._candidate_with_validated_proposals(candidate, report)
        target_state = self.validator.apply_delta(prepared.state, report.validated_delta)
        target_threads = self.validator.apply_thread_changes(
            prepared.threads,
            report.thread_changes,
            target_revision=target_state.revision,
        )
        target_state = target_state.model_copy(
            update={
                "active_threads": {
                    key: {
                        "status": item.status,
                        "description": item.description,
                        "urgency": item.urgency,
                    }
                    for key, item in target_threads.threads.items()
                    if item.status not in {"resolved", "abandoned"}
                }
            }
        )
        target_memories = self._target_memories(
            prepared.memories,
            candidate,
            section_id=transaction.section_id,
            revision=target_state.revision,
        )
        chapter, section = self.sections.next_position()
        goal = prepared.goal
        section_record = TickSection(
            id=transaction.section_id,
            chapter=chapter,
            section=section,
            title=candidate.title or candidate.section_summary[:24],
            content=candidate.narrative_text,
            word_count=sum(1 for char in candidate.narrative_text if not char.isspace()),
            tick_start=0,
            tick_end=0,
            tick_count=0,
            generation_mode=generation_mode,
            transaction_id=transaction.id,
            story_bible_revision=prepared.bible.revision,
            canonical_state_revision=target_state.revision,
            validation_report=report.model_dump(mode="json"),
            section_goal=goal.model_dump(mode="json"),
            editor_trace={
                "section_summary": candidate.section_summary,
                "context_manifest": prepared.context.manifest.model_dump(mode="json"),
                "consistency_notes": candidate.consistency_notes,
            },
            created_at=TickSection.now_iso(),
        )
        staged = transaction.model_copy(
            update={
                "phase": "validated",
                "candidate": candidate,
                "narrative_contract": prepared.narrative_contract,
                "section_budget_plan": prepared.section_budget_plan,
                "narrative_validation_report": narrative_report,
                "final_length_report": final_length_report,
                "final_ending_report": final_ending_report,
                "final_balance_report": final_balance_report,
                "validation_report": report,
                "style_validation_report": self._style_report(
                    prepared, candidate, narrative_report
                ),
                "base_canonical_state": prepared.state.model_dump(mode="json"),
                "base_story_threads": prepared.threads.model_dump(mode="json"),
                "base_memory_repository": prepared.memories.model_dump(mode="json"),
                "target_canonical_state": target_state.model_dump(mode="json"),
                "target_story_threads": target_threads.model_dump(mode="json"),
                "target_memory_repository": target_memories.model_dump(mode="json"),
                "section_record": section_record.model_dump(mode="json"),
                "updated_at": utc_now(),
            }
        )
        return self.transactions.save(staged)

    @staticmethod
    def _candidate_with_validated_proposals(
        candidate: WriterCandidate,
        report: ValidationReport,
    ) -> WriterCandidate:
        """Keep prose, but retain only server-revalidated authority proposals."""
        opened = []
        advanced = []
        resolved = []
        for change in report.thread_changes:
            if change.action == "opened":
                opened.append(change.thread)
            elif change.action == "advanced":
                advanced.append(change.thread)
            else:
                resolved.append(change.thread)
        return candidate.model_copy(
            update={
                "state_delta": list(report.validated_delta),
                "threads_opened": opened,
                "threads_advanced": advanced,
                "threads_resolved": resolved,
            }
        )

    def _commit_staged(self, transaction: GenerationTransaction) -> None:
        if not (
            transaction.target_canonical_state
            and transaction.target_story_threads
            and transaction.target_memory_repository
            and transaction.section_record
        ):
            raise ValueError("transaction has no complete staged snapshot")
        # Hold the same per-file lock used by StoryBible PUT for the complete
        # commit window.  This closes the check-then-write race in-process.
        with self.bibles.lock:
            current_bible = self.bibles.load()
            if current_bible.revision != transaction.story_bible_revision:
                stale = self._mark_stale_and_rollback(
                    transaction, current_bible.revision
                )
                raise StaleStoryBibleError(stale)

            current_revision = self.states.load().revision
            try:
                if transaction.phase == "committing":
                    self.revision_guard.ensure_recovery(
                        transaction,
                        current_revision=current_revision,
                    )
                else:
                    self.revision_guard.ensure_commit(
                        transaction,
                        current_revision=current_revision,
                    )
            except RevisionGuardError as exc:
                broken = self._mark_revision_chain_broken(transaction, exc)
                raise RevisionChainBrokenError(broken) from exc

            committing = transaction.model_copy(
                update={"phase": "committing", "updated_at": utc_now()}
            )
            self.transactions.save(committing)
            target_state = CanonicalState.model_validate(committing.target_canonical_state)
            target_threads = StoryThreadRepository.model_validate(
                committing.target_story_threads
            )
            target_memories = MemoryRepositoryState.model_validate(
                committing.target_memory_repository
            )
            section = TickSection.model_validate(committing.section_record)

            self._save_revision_target(
                self.states,
                target_state,
                base_revision=committing.canonical_state_revision,
            )
            if committing.journal_canonical_revision != target_state.revision:
                committing = committing.model_copy(
                    update={
                        "journal_canonical_revision": target_state.revision,
                        "updated_at": utc_now(),
                    }
                )
                self.transactions.save(committing)
            self._save_revision_target(
                self.threads,
                target_threads,
                base_revision=target_threads.revision - 1,
            )
            self._save_revision_target(
                self.memories,
                target_memories,
                base_revision=target_memories.revision - 1,
            )
            self.sections.append_idempotent(section)
            committed = committing.model_copy(
                update={
                    "phase": "committed",
                    "committed": True,
                    "updated_at": utc_now(),
                }
            )
            self.transactions.save(committed)

    def _mark_revision_chain_broken(
        self,
        transaction: GenerationTransaction,
        error: RevisionGuardError,
    ) -> GenerationTransaction:
        report = error.report
        broken = transaction.model_copy(
            update={
                "phase": "rejected",
                "committed": False,
                "error_code": "REVISION_CHAIN_BROKEN",
                "error": (
                    "事务修订链不一致，拒绝提交或恢复："
                    f"expected={report.expected_revision}, "
                    f"journal={report.journal_revision}, "
                    f"canonical={report.current_revision}, "
                    f"target={report.target_revision}"
                ),
                "updated_at": utc_now(),
            }
        )
        return self.transactions.save(broken)

    def _mark_stale_and_rollback(
        self, transaction: GenerationTransaction, actual_revision: int
    ) -> GenerationTransaction:
        rollback_errors: list[str] = []
        try:
            self.sections.remove_by_transaction_id(transaction.id)
        except Exception as exc:
            rollback_errors.append(f"section rollback: {exc}")
        for label, store, base_payload, target_payload in (
            (
                "canonical",
                self.states,
                transaction.base_canonical_state,
                transaction.target_canonical_state,
            ),
            (
                "threads",
                self.threads,
                transaction.base_story_threads,
                transaction.target_story_threads,
            ),
            (
                "memory",
                self.memories,
                transaction.base_memory_repository,
                transaction.target_memory_repository,
            ),
        ):
            if not base_payload or not target_payload:
                continue
            current = store.load()
            current_payload = current.model_dump(mode="json")
            if current_payload == base_payload:
                continue
            if current_payload != target_payload:
                rollback_errors.append(f"{label} revision moved beyond transaction")
                continue
            store.save(current.__class__.model_validate(base_payload))
        error = (
            "创作圣经在生成期间发生了变化。本次候选基于旧版本，未提交，请重新生成。"
        )
        if rollback_errors:
            error += " 回滚检查: " + "；".join(rollback_errors)
        stale = transaction.model_copy(
            update={
                "phase": "stale_context",
                "committed": False,
                "error_code": "STORY_BIBLE_REVISION_STALE",
                "error": error,
                "updated_at": utc_now(),
            }
        )
        return self.transactions.save(stale)

    @staticmethod
    def _save_revision_target(store, target, *, base_revision: int) -> None:
        current = store.load()
        if current.revision == target.revision:
            if current.model_dump(mode="json") != target.model_dump(mode="json"):
                raise RevisionConflict(base_revision, current.revision)
            return
        if current.revision != base_revision:
            raise RevisionConflict(base_revision, current.revision)
        store.save(target)

    @staticmethod
    def _target_memories(
        current: MemoryRepositoryState,
        candidate: WriterCandidate,
        *,
        section_id: str,
        revision: int,
    ) -> MemoryRepositoryState:
        payload = copy.deepcopy(current.model_dump(mode="python"))
        records = payload["records"]
        automatic = MemoryRecord(
            id=f"section_summary_{section_id}",
            type="event",
            section_id=section_id,
            summary=candidate.section_summary,
            importance=7,
            canon_status="confirmed",
            source_refs=[section_id],
            created_at_revision=revision,
        )
        records[automatic.id] = automatic.model_dump(mode="python")
        for memory in candidate.memory_records:
            records[memory.id] = memory.model_copy(
                update={
                    "section_id": memory.section_id or section_id,
                    "created_at_revision": revision,
                }
            ).model_dump(mode="python")
        payload["revision"] = current.revision + 1
        payload["updated_at"] = utc_now()
        return MemoryRepositoryState.model_validate(payload)

    @staticmethod
    def _merge_usage(
        left: dict[str, int],
        right: dict[str, int],
        *,
        phase: str = "repair",
    ) -> dict[str, int]:
        merged = {
            key: int(left.get(key, 0)) + int(right.get(key, 0))
            for key in set(left) | set(right)
        }
        phase_key = "retry_tokens" if phase == "retry" else "repair_tokens"
        merged[phase_key] = int(left.get(phase_key, 0)) + int(
            right.get("total_tokens", 0)
        )
        return merged


__all__ = [
    "AuthorGenerationService",
    "CommitPendingError",
    "GenerationRejected",
    "PreparedGeneration",
    "RevisionChainBrokenError",
    "StaleStoryBibleError",
]
