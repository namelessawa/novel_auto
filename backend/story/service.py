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
from story.repair_plan import (
    DeterministicRepairEnforcer,
    RepairPlan,
    RepairPlanBuilder,
    RepairRegressionValidator,
)
from story.validator import StoryValidator
from story.writer import AuthorWriter, WriterProtocol, WriterResult

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


@dataclass(frozen=True)
class PreparedGeneration:
    bible: StoryBible
    state: CanonicalState
    threads: StoryThreadRepository
    memories: MemoryRepositoryState
    goal: SectionGoal
    narrative_contract: NarrativeContract
    event_execution_plan: EventExecutionPlan
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
        self.repair_plan_builder = repair_plan_builder or RepairPlanBuilder()
        self.repair_regression_validator = RepairRegressionValidator()
        self.repair_enforcer = DeterministicRepairEnforcer()
        self.context_builder = context_builder or ContextBuilder()
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
                narrative_report = self.validate_narrative(prepared, candidate)
                strict_report = self.validate(prepared, candidate)
                report = strict_report
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
                        "updated_at": utc_now(),
                    }
                )
                self.transactions.save(transaction)

                # Repair has prose authority only and is triggered only by prose
                # contract findings. Invalid optional delta/thread proposals are
                # deterministically dropped instead of asking the model to rewrite them.
                if (
                    narrative_report.violations
                    and narrative_report.repairable
                ):
                    repair_plan = self._repair_plan(
                        prepared,
                        transaction,
                        candidate,
                        narrative_report,
                        strict_report,
                    )
                    transaction = transaction.model_copy(
                        update={"repair_plan": repair_plan, "updated_at": utc_now()}
                    )
                    self.transactions.save(transaction)
                    original_candidate = candidate
                    repaired = await self.repair(candidate, repair_plan)
                    # Enforce prose-only authority at the service boundary too;
                    # custom/recorded WriterProtocol implementations cannot bypass it.
                    candidate = original_candidate.model_copy(
                        update={
                            "narrative_text": repaired.candidate.narrative_text,
                        }
                    )
                    transaction = transaction.model_copy(
                        update={
                            "candidate": candidate,
                            "candidate_history": [
                                *transaction.candidate_history,
                                candidate,
                            ],
                            "writer_calls": 2,
                            "repair_performed": True,
                            "repair_ignored_fields": repaired.ignored_fields,
                            "usage": self._merge_usage(transaction.usage, repaired.usage),
                            "updated_at": utc_now(),
                        }
                    )
                    self.transactions.save(transaction)
                    narrative_report = self.validate_narrative(prepared, candidate)
                    enforced_removals: list[dict[str, str]] = []
                    # One model Repair call is the hard cap.  If it replaces one
                    # unsupported addition with another, remove only the exact
                    # validator-proven clause, then revalidate.  This bounded
                    # deterministic pass has no authority over any other code.
                    for _ in range(8):
                        cleaned_text, removals = self.repair_enforcer.enforce(
                            report=narrative_report,
                            narrative_text=candidate.narrative_text,
                        )
                        if not removals:
                            break
                        enforced_removals.extend(removals)
                        candidate = candidate.model_copy(
                            update={"narrative_text": cleaned_text}
                        )
                        narrative_report = self.validate_narrative(prepared, candidate)
                    if enforced_removals:
                        transaction = transaction.model_copy(
                            update={
                                "candidate": candidate,
                                "candidate_history": [
                                    *transaction.candidate_history,
                                    candidate,
                                ],
                                "repair_enforced_removals": enforced_removals,
                                "updated_at": utc_now(),
                            }
                        )
                        self.transactions.save(transaction)
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
                    report = self.validate(
                        prepared,
                        candidate,
                        drop_unsupported_proposals=True,
                    )
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
            narrative_report = self.validate_narrative(prepared, candidate)
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
        try:
            context = self.context_builder.build(
                novel_id=self.novel_id,
                section_id=section_id,
                story_bible=bible,
                canonical_state=state,
                narrative_contract=narrative_contract,
                event_execution_plan=event_execution_plan,
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
            narrative_contract=narrative_contract,
            event_execution_plan=event_execution_plan,
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

    async def generate(self, prepared: PreparedGeneration) -> WriterResult:
        return await self.writer.generate(prepared.context, prepared.goal)

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
    ) -> NarrativeValidationReport:
        return self.narrative_validator.validate(
            prepared.narrative_contract,
            candidate.narrative_text,
            event_execution_plan=prepared.event_execution_plan,
            event_evidence=candidate.event_evidence,
            end_state_evidence=candidate.end_state_evidence,
        )

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
    ) -> RepairPlan:
        return self.repair_plan_builder.build(
            transaction_id=transaction.id,
            contract=prepared.narrative_contract,
            event_plan=prepared.event_execution_plan,
            narrative_report=narrative_report,
            state_report=state_report,
            narrative_text=candidate.narrative_text,
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
        narrative_report = self.validate_narrative(prepared, candidate)
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
                "narrative_validation_report": narrative_report,
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
    def _merge_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
        merged = {
            key: int(left.get(key, 0)) + int(right.get(key, 0))
            for key in set(left) | set(right)
        }
        merged["repair_tokens"] = int(left.get("repair_tokens", 0)) + int(
            right.get("total_tokens", 0)
        )
        return merged


__all__ = [
    "AuthorGenerationService",
    "CommitPendingError",
    "GenerationRejected",
    "PreparedGeneration",
    "StaleStoryBibleError",
]
