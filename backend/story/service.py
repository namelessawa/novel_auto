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
from story.context_builder import ContextBuilder, ContextPackage
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
from story.persistence import (
    CanonicalStateStore,
    ContextManifestStore,
    GenerationTransactionStore,
    MemoryRepository,
    RevisionConflict,
    StoryBibleStore,
    StoryThreadStore,
)
from story.validator import StoryValidator
from story.writer import AuthorWriter, WriterProtocol, WriterResult

logger = logging.getLogger(__name__)


class GenerationRejected(RuntimeError):
    def __init__(self, transaction: GenerationTransaction) -> None:
        super().__init__("candidate rejected by StoryValidator")
        self.transaction = transaction


class CommitPendingError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedGeneration:
    bible: StoryBible
    state: CanonicalState
    threads: StoryThreadRepository
    memories: MemoryRepositoryState
    goal: SectionGoal
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
                report = self.validate(prepared, generated.candidate)
                candidate = generated.candidate

                # Medium findings are eligible for the same one targeted repair;
                # no Critic loop is created and writer_calls can never exceed two.
                if report.violations and report.repairable:
                    repaired = await self.repair(candidate, report)
                    candidate = repaired.candidate
                    transaction = transaction.model_copy(
                        update={
                            "candidate": candidate,
                            "writer_calls": 2,
                            "repair_performed": True,
                            "usage": self._merge_usage(transaction.usage, repaired.usage),
                            "updated_at": utc_now(),
                        }
                    )
                    self.transactions.save(transaction)
                    report = self.validate(prepared, candidate)

                if not report.accepted:
                    rejected = transaction.model_copy(
                        update={
                            "phase": "rejected",
                            "candidate": candidate,
                            "validation_report": report,
                            "error": "高置信一致性冲突在一次修复后仍存在",
                            "updated_at": utc_now(),
                        }
                    )
                    self.transactions.save(rejected)
                    raise GenerationRejected(rejected)

                staged = self._stage(prepared, transaction, candidate, report)
                self.commit(staged)
                novel_manager.touch_last_accessed(self.user_id, self.novel_id)
                return self.transactions.load(staged.id)
            except GenerationRejected:
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
                if existing.phase in {"validated", "committing"}:
                    self._commit_staged(existing)
                    return self.transactions.load(request_id)
                raise CommitPendingError(
                    f"transaction {request_id} already exists in phase {existing.phase}"
                )

            prepared = self.prepare(goal, request_id=request_id)
            transaction = prepared.transaction.model_copy(
                update={
                    "phase": "generated",
                    "candidate": candidate,
                    "writer_calls": 0,
                    "updated_at": utc_now(),
                }
            )
            self.transactions.save(transaction)
            report = self.validate(
                prepared,
                candidate,
                source_mode=generation_mode,
            )
            if not report.accepted:
                rejected = transaction.model_copy(
                    update={
                        "phase": "rejected",
                        "validation_report": report,
                        "error": "外部候选未通过统一一致性校验",
                        "updated_at": utc_now(),
                    }
                )
                return self.transactions.save(rejected)

            staged = self._stage(
                prepared,
                transaction,
                candidate,
                report,
                generation_mode=generation_mode,
            )
            self.commit(staged)
            novel_manager.touch_last_accessed(self.user_id, self.novel_id)
            return self.transactions.load(staged.id)

    def prepare(self, goal: SectionGoal, *, request_id: str) -> PreparedGeneration:
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
        context = self.context_builder.build(
            novel_id=self.novel_id,
            section_id=section_id,
            story_bible=bible,
            canonical_state=state,
            section_goal=prepared_goal,
            story_threads=list(threads.threads.values()),
            previous_prose_tail=previous_tail,
            recent_summaries=recent_summaries,
            long_term_memories=long_memories,
        )
        self.manifests.save(context.manifest)
        transaction = GenerationTransaction(
            id=request_id,
            user_id=self.user_id,
            novel_id=self.novel_id,
            section_id=section_id,
            story_bible_revision=bible.revision,
            canonical_state_revision=state.revision,
            target_canonical_revision=state.revision + 1,
            context_manifest=context.manifest,
        )
        self.transactions.save(transaction)
        return PreparedGeneration(
            bible=bible,
            state=state,
            threads=threads,
            memories=memories,
            goal=prepared_goal,
            context=context,
            transaction=transaction,
        )

    async def generate(self, prepared: PreparedGeneration) -> WriterResult:
        return await self.writer.generate(prepared.context, prepared.goal)

    def validate(
        self,
        prepared: PreparedGeneration,
        candidate: WriterCandidate,
        *,
        source_mode: str = "author",
    ) -> ValidationReport:
        return self.validator.validate(
            bible=prepared.bible,
            state=prepared.state,
            threads=prepared.threads,
            goal=prepared.goal,
            candidate=candidate,
            source_mode=source_mode,
        )

    async def repair(
        self,
        candidate: WriterCandidate,
        report: ValidationReport,
    ) -> WriterResult:
        return await self.writer.repair(candidate, report)

    def commit(self, transaction: GenerationTransaction) -> None:
        self._commit_staged(transaction)

    def recover(self) -> list[str]:
        recovered: list[str] = []
        for transaction in self.transactions.list_pending():
            try:
                self._commit_staged(transaction)
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
                "validation_report": report,
                "target_canonical_state": target_state.model_dump(mode="json"),
                "target_story_threads": target_threads.model_dump(mode="json"),
                "target_memory_repository": target_memories.model_dump(mode="json"),
                "section_record": section_record.model_dump(mode="json"),
                "updated_at": utc_now(),
            }
        )
        return self.transactions.save(staged)

    def _commit_staged(self, transaction: GenerationTransaction) -> None:
        if not (
            transaction.target_canonical_state
            and transaction.target_story_threads
            and transaction.target_memory_repository
            and transaction.section_record
        ):
            raise ValueError("transaction has no complete staged snapshot")
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
        return {
            key: int(left.get(key, 0)) + int(right.get(key, 0))
            for key in set(left) | set(right)
        }


__all__ = [
    "AuthorGenerationService",
    "CommitPendingError",
    "GenerationRejected",
    "PreparedGeneration",
]
