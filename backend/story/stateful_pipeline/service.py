"""Chapter generation pipeline orchestrator.

The pipeline owns orchestration only:

  1. user confirmation gate (immutable authority freeze)
  2. chapter goal resolution from the frozen synopsis + BookOutline anchor
  3. foreshadow selection (deterministic, receipt-persisted)
  4. handing the chapter to the single official Author production chain
  5. derived extraction/integration over the *committed* prose
  6. verifying the Author commit before declaring COMPLETED

Official prose, CanonicalState, StoryThreads, MemoryRepository and the
transaction journal are written exclusively by
:class:`story.service.AuthorGenerationService`.  This service never writes
them, so ``COMPLETED`` always corresponds to a real committed manuscript.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from story.models import (
    CanonicalState,
    MemoryRepositoryState,
    StoryBible,
    StoryThreadRepository,
)
from story.persistence import (
    CanonicalStateStore,
    MemoryRepository,
    StoryBibleStore,
    StoryThreadStore,
)
from story.production_models import BookOutline
from story.production_persistence import BookOutlineStore
from story.stateful_pipeline.author_bridge import (
    AuthorChapterCommit,
    author_request_id,
    build_section_goal,
    resolve_chapter_intent,
    verify_author_commit,
)
from story.stateful_pipeline.chroma_repository import ChromaMemoryRepository
from story.stateful_pipeline.foreshadow_selection import (
    ForeshadowSelectionService,
)
from story.stateful_pipeline.llm_roles import (
    extract_foreshadows,
    extract_information,
    generate_information_schema,
    generate_synopsis,
    integrate_memory,
    render_story_bible_prompt,
    story_bible_prompt_view,
)
from story.stateful_pipeline.models import (
    AuthorityRevisions,
    ChapterConfirmation,
    ChapterGenerationPreference,
    ChapterInformation,
    ChapterPipelinePhase,
    ChapterPipelineState,
    ChapterSynopsis,
    ForeshadowRecord,
    ForeshadowSelectionReceipt,
    ForeshadowSelectionState,
    ForeshadowStatus,
    InformationSchema,
    MemoryIntegrationRecord,
    utc_now,
)
from story.stateful_pipeline.persistence import (
    ChapterInformationStore,
    ForeshadowStore,
    InformationSchemaStore,
    MemoryIntegrationStore,
    PipelineStateStore,
    SynopsisStore,
    TransferContextStore,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps imports light
    from story.service import AuthorGenerationService

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Raised when pipeline encounters an unrecoverable error."""


class ConfirmationRequiredError(PipelineError):
    """Raised when generation is attempted without user confirmation."""


class ConfirmationStaleError(PipelineError):
    """Raised when a frozen confirmation no longer matches live authorities.

    Generation fails closed instead of silently binding to the newer revision.
    """


class CommitPendingError(PipelineError):
    """The Author journal may still commit this transaction; replay it."""


@dataclass(frozen=True)
class _Authorities:
    """Live authority documents plus the revisions the pipeline freezes."""

    bible: StoryBible
    canon: CanonicalState
    threads: StoryThreadRepository
    memories: MemoryRepositoryState
    outline: BookOutline | None
    outline_revision: int
    style_revision: int
    schema_revision: int


class StatefulPipelineService:
    """Orchestrates chapter generation on top of Author production.

    This service coordinates:
      - user confirmation gates and the immutable authority freeze
      - deterministic foreshadow selection
      - the single official Author generation + commit boundary
      - derived extraction roles over committed prose
      - ChromaDB integration, state persistence and recovery
    """

    def __init__(self, data_dir: str, chroma_repo: ChromaMemoryRepository | None = None):
        self._data_dir = data_dir
        self._chroma = chroma_repo or ChromaMemoryRepository()
        self._selection_service = ForeshadowSelectionService()

        # Pipeline-owned derived stores
        self._synopsis_store = SynopsisStore(data_dir)
        self._foreshadow_store = ForeshadowStore(data_dir)
        self._info_store = ChapterInformationStore(data_dir)
        self._transfer_store = TransferContextStore(data_dir)
        self._pipeline_store = PipelineStateStore(data_dir)
        self._integration_store = MemoryIntegrationStore(data_dir)
        self._schema_store = InformationSchemaStore(data_dir)

        # Author authorities — read only; the Author chain owns every write.
        self._bible_store = StoryBibleStore(data_dir)
        self._canon_store = CanonicalStateStore(data_dir)
        self._thread_store = StoryThreadStore(data_dir)
        self._memory_store = MemoryRepository(data_dir)
        self._outline_store = BookOutlineStore(data_dir)

    # ------------------------------------------------------------------
    # Synopsis Management
    # ------------------------------------------------------------------

    async def generate_initial_synopses(
        self,
        novel_id: str,
        story_bible: StoryBible,
        genre: str,
    ) -> list[ChapterSynopsis]:
        """Generate synopses for chapters 1 and 2."""
        bible_summary = render_story_bible_prompt(story_bible_prompt_view(story_bible))

        items = await generate_synopsis(
            novel_id=novel_id,
            story_bible_summary=bible_summary,
            genre=genre,
            chapter_numbers=[1, 2],
        )

        synopses = []
        for item in items:
            chapter = item.get("chapter", len(synopses) + 1)
            synopsis = ChapterSynopsis(
                novel_id=novel_id,
                chapter_number=chapter,
                title=item.get("title", ""),
                synopsis=item.get("synopsis", ""),
            )
            self._synopsis_store.save(synopsis)
            synopses.append(synopsis)

        return synopses

    def get_synopsis(self, novel_id: str, chapter: int) -> ChapterSynopsis | None:
        return self._synopsis_store.load(novel_id, chapter)

    def update_synopsis(
        self,
        novel_id: str,
        chapter: int,
        title: str | None = None,
        synopsis: str | None = None,
    ) -> ChapterSynopsis:
        """Update synopsis (user edit). Creates new revision."""
        existing = self._synopsis_store.load(novel_id, chapter)
        if existing is None:
            existing = ChapterSynopsis(
                novel_id=novel_id,
                chapter_number=chapter,
            )

        updates: dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if synopsis is not None:
            updates["synopsis"] = synopsis
        updates["revision"] = existing.revision + 1

        updated = existing.model_copy(update=updates)
        return self._synopsis_store.save(updated)

    # ------------------------------------------------------------------
    # Information Schema Management
    # ------------------------------------------------------------------

    def get_schema(self, novel_id: str) -> InformationSchema | None:
        return self._schema_store.load(novel_id)

    async def ensure_schema(
        self,
        novel_id: str,
        story_bible: StoryBible,
        genre: str,
        synopses: list[ChapterSynopsis],
    ) -> InformationSchema:
        """Get or auto-generate information schema."""
        existing = self._schema_store.load(novel_id)
        if existing is not None:
            return existing

        bible_summary = render_story_bible_prompt(story_bible_prompt_view(story_bible))
        synopsis_texts = [s.synopsis for s in synopses]

        fields = await generate_information_schema(
            novel_id=novel_id,
            story_bible_summary=bible_summary,
            genre=genre,
            chapter_synopses=synopsis_texts,
        )

        schema = InformationSchema(
            novel_id=novel_id,
            revision=1,
            fields=fields,
            source="auto_generated",
        )
        return self._schema_store.save(schema)

    def update_schema(
        self,
        novel_id: str,
        fields: list[dict[str, Any]],
    ) -> InformationSchema:
        """Update schema fields (user edit). Creates new revision."""
        from story.stateful_pipeline.models import InformationField

        field_objects = []
        for i, f in enumerate(fields):
            field_objects.append(
                InformationField(
                    key=f.get("key", f"field_{i}"),
                    name=f.get("name", f.get("key", f"字段{i}")),
                    description=f.get("description", ""),
                    order=i,
                )
            )

        existing = self._schema_store.load(novel_id)
        revision = (existing.revision + 1) if existing else 1

        schema = InformationSchema(
            novel_id=novel_id,
            revision=revision,
            fields=field_objects,
            source="user_defined",
        )
        return self._schema_store.save(schema)

    # ------------------------------------------------------------------
    # Foreshadow Management
    # ------------------------------------------------------------------

    def get_foreshadows(self, novel_id: str) -> list[ForeshadowRecord]:
        return self._foreshadow_store.load_records(novel_id)

    def get_foreshadow_state(self, novel_id: str) -> ForeshadowSelectionState:
        return self._foreshadow_store.load_state(novel_id)

    def get_selection_receipt(self, novel_id: str, chapter: int):
        return self._foreshadow_store.load_receipt(novel_id, chapter)

    # ------------------------------------------------------------------
    # Chapter Confirmation
    # ------------------------------------------------------------------

    def confirm_chapter(
        self,
        novel_id: str,
        chapter: int,
        preference: ChapterGenerationPreference,
        *,
        attempt: int = 1,
    ) -> ChapterConfirmation:
        """Freeze every authority the chapter will be generated against.

        Moves the pipeline to ``CONFIRMED``.  Generation binds to this snapshot
        and fails closed when a live authority has since moved.
        """
        authorities = self._load_authorities(novel_id)
        synopsis = self._synopsis_store.load(novel_id, chapter)

        confirmation = ChapterConfirmation(
            novel_id=novel_id,
            chapter_number=chapter,
            synopsis_revision=synopsis.revision if synopsis else 0,
            synopsis_title=synopsis.title if synopsis else "",
            synopsis_text=synopsis.synopsis if synopsis else "",
            story_bible_revision=authorities.bible.revision,
            canon_revision=authorities.canon.revision,
            story_thread_revision=authorities.threads.revision,
            memory_revision=authorities.memories.revision,
            outline_revision=authorities.outline_revision,
            style_revision=authorities.style_revision,
            information_schema_revision=authorities.schema_revision,
        )

        state = ChapterPipelineState(
            novel_id=novel_id,
            chapter_number=chapter,
            phase=ChapterPipelinePhase.CONFIRMED,
            attempt=max(1, attempt),
            synopsis_revision=confirmation.synopsis_revision,
            synopsis_title=confirmation.synopsis_title,
            synopsis_text=confirmation.synopsis_text,
            story_bible_revision=confirmation.story_bible_revision,
            canon_revision=confirmation.canon_revision,
            story_thread_revision=confirmation.story_thread_revision,
            memory_revision=confirmation.memory_revision,
            outline_revision=confirmation.outline_revision,
            style_revision=confirmation.style_revision,
            information_schema_revision=confirmation.information_schema_revision,
            generation_preference=preference,
            started_at=utc_now(),
        )
        self._pipeline_store.save(state)
        return confirmation

    def retry_chapter(
        self,
        novel_id: str,
        chapter: int,
        preference: ChapterGenerationPreference | None = None,
    ) -> ChapterConfirmation:
        """Create a fresh attempt for a FAILED or COMPLETED chapter.

        The whole chain re-executes: derived artifacts for this chapter are
        purged and the Author transaction id changes, so a retry can never mix
        new prose with cached information or memory.
        """
        state = self._pipeline_store.load(novel_id, chapter)
        if state is None:
            raise PipelineError(f"第 {chapter} 章尚未确认，无法 retry")
        if state.phase not in (
            ChapterPipelinePhase.FAILED,
            ChapterPipelinePhase.COMPLETED,
        ):
            raise PipelineError(
                f"第 {chapter} 章当前处于 {state.phase.value}，只有 failed / "
                f"chapter_completed 章节可以 retry"
            )
        resolved = preference or state.generation_preference or ChapterGenerationPreference(
            novel_id=novel_id,
            chapter_number=chapter,
        )
        self.purge_chapter_derived(novel_id, chapter)
        return self.confirm_chapter(
            novel_id,
            chapter,
            resolved,
            attempt=state.attempt + 1,
        )

    def purge_chapter_derived(self, novel_id: str, chapter: int) -> None:
        """Drop this chapter's derived pipeline artifacts (explicit retry only)."""

        records = [
            record
            for record in self._foreshadow_store.load_records(novel_id)
            if record.source_chapter != chapter
        ]
        self._foreshadow_store.save_records(records)
        self._foreshadow_store.delete_receipt(novel_id, chapter)
        self._info_store.delete(novel_id, chapter)
        self._transfer_store.delete(novel_id, chapter)
        self._integration_store.delete(novel_id, chapter)

    # ------------------------------------------------------------------
    # Pipeline Execution
    # ------------------------------------------------------------------

    def _require_started_state(self, novel_id: str, chapter: int) -> ChapterPipelineState:
        """Load the pipeline state, refusing unconfirmed and failed chapters.

        Shared by the synchronous API gate and the runner so both reject with
        identical semantics and provably zero Writer calls.
        """
        state = self._pipeline_store.load(novel_id, chapter)
        if state is None or state.phase == ChapterPipelinePhase.AWAITING_CONFIRMATION:
            raise ConfirmationRequiredError(
                f"Chapter {chapter} requires user confirmation before generation"
            )
        if state.phase == ChapterPipelinePhase.FAILED:
            raise PipelineError(
                f"第 {chapter} 章上一次生成失败（{state.error_message or 'unknown'}）；"
                f"请通过 retry 创建新的 attempt"
            )
        return state

    def assert_generation_allowed(self, novel_id: str, chapter: int) -> ChapterPipelineState:
        """Synchronous gate: same rules as :meth:`run_chapter_pipeline`.

        Lets the API reject an unconfirmed, failed or stale chapter before any
        task is queued, so a rejected request provably costs zero Writer calls.
        """
        state = self._require_started_state(novel_id, chapter)
        if state.phase in (
            ChapterPipelinePhase.COMPLETED,
            ChapterPipelinePhase.WRITING,
            ChapterPipelinePhase.EXTRACTING_FORESHADOWS,
            ChapterPipelinePhase.EXTRACTING_INFORMATION,
            ChapterPipelinePhase.INTEGRATING_MEMORY,
            ChapterPipelinePhase.COMMITTING,
        ):
            # Either already committed, or the Author chain already owns this
            # attempt; run_chapter_pipeline replays it from the journal.
            return state

        confirmation = state.frozen_confirmation()
        if confirmation is None:
            raise ConfirmationRequiredError(
                f"Chapter {chapter} has no frozen confirmation binding"
            )
        self._assert_frozen(
            novel_id,
            chapter,
            confirmation,
            self._load_authorities(novel_id),
        )
        return state

    async def run_chapter_pipeline(
        self,
        novel_id: str,
        chapter: int,
        *,
        author_service: AuthorGenerationService,
    ) -> ChapterPipelineState:
        """Execute the chapter pipeline on top of Author production.

        Phases:
          confirmed → preparing_context → writing → extracting_foreshadows →
          extracting_information → integrating_memory → committing → completed

        ``COMPLETED`` is reached only after the Author transaction committed and
        the committed manuscript plus advanced authorities were re-read from
        disk.  Anything else ends in ``FAILED`` (or re-raises a confirmation
        problem without consuming a Writer call).
        """
        state = self._require_started_state(novel_id, chapter)
        if state.phase == ChapterPipelinePhase.COMPLETED:
            return self._replay_completed(novel_id, chapter, state, author_service)

        confirmation = state.frozen_confirmation()
        if confirmation is None:
            raise ConfirmationRequiredError(
                f"Chapter {chapter} has no frozen confirmation binding"
            )

        authorities = self._load_authorities(novel_id)
        publish_errors = authorities.bible.publish_errors()
        if publish_errors:
            raise PipelineError(
                "StoryBible 尚不可用于正式生成: " + "；".join(publish_errors)
            )

        request_id = author_request_id(novel_id, chapter, state.attempt)
        resuming_committed = self._transaction_committed(author_service, request_id)
        if not resuming_committed:
            self._assert_frozen(novel_id, chapter, confirmation, authorities)

        try:
            state = self._transition(state, ChapterPipelinePhase.PREPARING_CONTEXT)
            receipt = self._prepare_foreshadow_decisions(novel_id, chapter, state)

            state = self._transition(
                state,
                ChapterPipelinePhase.WRITING,
                author_transaction_id=request_id,
            )
            transaction = await self._run_author_chapter(
                author_service=author_service,
                novel_id=novel_id,
                chapter=chapter,
                confirmation=confirmation,
                authorities=authorities,
                receipt=receipt,
                request_id=request_id,
            )
            prose = self._committed_prose(author_service, transaction)

            state = self._transition(state, ChapterPipelinePhase.EXTRACTING_FORESHADOWS)
            await self._extract_foreshadows(novel_id, chapter, prose, state)

            state = self._transition(state, ChapterPipelinePhase.EXTRACTING_INFORMATION)
            information = await self._extract_information(novel_id, chapter, prose, state)

            state = self._transition(state, ChapterPipelinePhase.INTEGRATING_MEMORY)
            await self._integrate_memory(novel_id, chapter, information, state)

            state = self._transition(state, ChapterPipelinePhase.COMMITTING)
            commit = verify_author_commit(
                transaction,
                prose=prose,
                canonical_revision_before=confirmation.canon_revision,
            )
            self._assert_authorities_committed(commit, confirmation)
        except ConfirmationStaleError:
            raise
        except CommitPendingError as exc:
            # Recoverable by design: keep the phase so a replay finishes the
            # same Author transaction, but surface why the chapter is stuck.
            self._pipeline_store.save(
                state.model_copy(update={"error_message": str(exc)[:2000]})
            )
            raise
        except Exception as exc:
            return self._fail(state, exc)

        return self._transition(
            state,
            ChapterPipelinePhase.COMPLETED,
            author_transaction_id=commit.transaction_id,
            committed_section_id=commit.section_id,
            committed_char_count=commit.char_count,
            committed_canonical_revision=commit.canonical_revision_after,
            committed_at=utc_now(),
            error_message=None,
        )

    # ------------------------------------------------------------------
    # Internal Phase Implementations
    # ------------------------------------------------------------------

    async def _run_author_chapter(
        self,
        *,
        author_service: AuthorGenerationService,
        novel_id: str,
        chapter: int,
        confirmation: ChapterConfirmation,
        authorities: _Authorities,
        receipt: ForeshadowSelectionReceipt | None,
        request_id: str,
    ):
        """Hand the chapter to the single official Author production chain."""

        from story.service import (
            CommitPendingError as AuthorCommitPendingError,
        )
        from story.service import (
            GenerationRejected,
            RevisionChainBrokenError,
            StaleStoryBibleError,
        )

        intent = resolve_chapter_intent(
            chapter=chapter,
            synopsis_title=confirmation.synopsis_title,
            synopsis_text=confirmation.synopsis_text,
            outline=authorities.outline,
            foreshadow_hint=self._foreshadow_hint(novel_id, receipt),
        )
        goal = build_section_goal(intent)
        try:
            return await author_service.run(goal, request_id=request_id)
        except GenerationRejected as exc:
            rejected = exc.transaction
            raise PipelineError(
                "Author 生成被拒绝，正文未提交: "
                f"{rejected.error_code or rejected.error or 'candidate rejected'}"
            ) from exc
        except (StaleStoryBibleError, RevisionChainBrokenError) as exc:
            raise PipelineError(f"Author 权威状态冲突: {exc}") from exc
        except AuthorCommitPendingError as exc:
            raise CommitPendingError(
                f"Author 事务 {request_id} 处于 committing，将在重放时恢复: {exc}"
            ) from exc

    @staticmethod
    def _transaction_committed(
        author_service: AuthorGenerationService,
        request_id: str,
    ) -> bool:
        if not author_service.transactions.exists(request_id):
            return False
        return bool(author_service.transactions.load(request_id).committed)

    @staticmethod
    def _committed_prose(author_service: AuthorGenerationService, transaction) -> str:
        """Read the official manuscript from the Author commit journal."""

        section = author_service.sections.get_by_id(transaction.section_id)
        if section is None or not section.content.strip():
            raise PipelineError(
                f"Author 事务 {transaction.id} 没有官方已提交正文（section "
                f"{transaction.section_id}）"
            )
        return section.content

    def _assert_authorities_committed(
        self,
        commit: AuthorChapterCommit,
        confirmation: ChapterConfirmation,
    ) -> None:
        """Re-read the authorities from disk; COMPLETED needs real movement."""

        canon = self._canon_store.load()
        if canon.revision != commit.canonical_revision_after:
            raise PipelineError(
                "CanonicalState 未推进到已提交目标版本："
                f"磁盘 {canon.revision}，事务目标 {commit.canonical_revision_after}"
            )
        threads = self._thread_store.load()
        if threads.revision < confirmation.story_thread_revision:
            raise PipelineError(
                "StoryThreadRepository 版本回退："
                f"{confirmation.story_thread_revision} → {threads.revision}"
            )
        memories = self._memory_store.load()
        if memories.revision < confirmation.memory_revision:
            raise PipelineError(
                "MemoryRepository 版本回退："
                f"{confirmation.memory_revision} → {memories.revision}"
            )

    def _replay_completed(
        self,
        novel_id: str,
        chapter: int,
        state: ChapterPipelineState,
        author_service: AuthorGenerationService,
    ) -> ChapterPipelineState:
        """Idempotent re-entry: verify the commit, change nothing, call nothing."""

        if not state.committed_manuscript:
            raise PipelineError(
                f"第 {chapter} 章标记为已完成但没有已提交正文记录；请 retry 重新生成"
            )
        section = author_service.sections.get_by_id(state.committed_section_id)
        if section is None or not section.content.strip():
            raise PipelineError(
                f"第 {chapter} 章的已提交正文 {state.committed_section_id} 已不可读；"
                f"请 retry 重新生成"
            )
        expected = state.committed_canonical_revision or 0
        canon = self._canon_store.load()
        if canon.revision < expected:
            raise PipelineError(
                f"第 {chapter} 章提交时的 CanonicalState 版本 {expected} 已丢失"
                f"（当前 {canon.revision}）"
            )
        return state

    def _fail(self, state: ChapterPipelineState, exc: Exception) -> ChapterPipelineState:
        message = str(exc) or type(exc).__name__
        logger.warning(
            "pipeline chapter %s failed: %s", state.chapter_number, type(exc).__name__
        )
        return self._transition(
            state,
            ChapterPipelinePhase.FAILED,
            error_message=message[:2000],
        )

    def _foreshadow_hint(
        self,
        novel_id: str,
        receipt: ForeshadowSelectionReceipt | None,
    ) -> str:
        """Selected foreshadow becomes an explicit directive in the goal."""

        if receipt is None or not receipt.collision_winner or receipt.discarded:
            return ""
        record = next(
            (
                item
                for item in self._foreshadow_store.load_records(novel_id)
                if item.id == receipt.collision_winner
            ),
            None,
        )
        if record is None:
            return ""
        return record.summary or record.source_text

    def _prepare_foreshadow_decisions(
        self,
        novel_id: str,
        chapter: int,
        state: ChapterPipelineState,
    ) -> ForeshadowSelectionReceipt | None:
        """Roll new-foreshadow count and select eligible foreshadows.

        Runs during preparing_context. All random decisions are persisted
        in a receipt so retry/restart never re-rolls.

        Idempotency: if the receipt already exists it is replayed only when
        its decisions were not yet applied to records (applied_to_records).
        """
        existing = self._foreshadow_store.load_receipt(novel_id, chapter)
        records = self._foreshadow_store.load_records(novel_id)
        selection_state = self._foreshadow_store.load_state(novel_id)

        if existing is not None:
            if not existing.applied_to_records:
                self._selection_service.apply_receipt_to_records(
                    existing, records, selection_state
                )
                marked = existing.model_copy(update={"applied_to_records": True})
                self._foreshadow_store.save_records(records)
                self._foreshadow_store.save_state(selection_state)
                self._foreshadow_store.save_receipt(marked)
                return marked
            return existing

        preference = state.generation_preference
        if preference is None:
            preference = ChapterGenerationPreference(
                novel_id=novel_id,
                chapter_number=chapter,
            )

        # Roll the new-foreshadow count once for this chapter (persisted below).
        count, count_roll = self._selection_service.determine_new_foreshadow_count(
            preference.foreshadow_mode,
            preference.foreshadow_fixed_count,
        )

        # Run selection over existing foreshadows (mutates records/state).
        receipt = self._selection_service.select_foreshadow(
            novel_id=novel_id,
            chapter=chapter,
            foreshadows=records,
            state=selection_state,
        )
        receipt = receipt.model_copy(
            update={
                "new_foreshadow_count": count,
                "new_foreshadow_roll": count_roll,
                "applied_to_records": True,
            }
        )

        self._foreshadow_store.save_records(records)
        self._foreshadow_store.save_state(selection_state)
        self._foreshadow_store.save_receipt(receipt)
        return receipt

    async def _extract_foreshadows(
        self,
        novel_id: str,
        chapter: int,
        prose_text: str,
        state: ChapterPipelineState,
    ) -> None:
        """Extract new foreshadows from the committed prose.

        The count was frozen in the receipt during preparing_context — this
        method never re-rolls. Record IDs are deterministic, so a retry after
        a crash between extraction and save does not duplicate records.
        """
        from story.stateful_pipeline.foreshadow_selection import MINIMUM_AGE

        receipt = self._foreshadow_store.load_receipt(novel_id, chapter)
        if receipt is not None:
            count = receipt.new_foreshadow_count
        else:
            # Defensive fallback: no receipt (direct phase invocation in
            # tests). Roll is not persisted in this path.
            preference = state.generation_preference
            if preference is None:
                preference = ChapterGenerationPreference(
                    novel_id=novel_id,
                    chapter_number=chapter,
                )
            count, _ = self._selection_service.determine_new_foreshadow_count(
                preference.foreshadow_mode,
                preference.foreshadow_fixed_count,
            )

        if count <= 0:
            return

        extracted = await extract_foreshadows(
            novel_id=novel_id,
            chapter_number=chapter,
            prose_text=prose_text,
            count=count,
        )

        records = self._foreshadow_store.load_records(novel_id)
        existing_ids = {r.id for r in records}
        changed = False
        for i, item in enumerate(extracted):
            record_id = f"{novel_id}:ch{chapter}:f{i + 1}"
            if record_id in existing_ids:
                continue  # retry dedup: already persisted
            records.append(
                ForeshadowRecord(
                    id=record_id,
                    novel_id=novel_id,
                    source_chapter=chapter,
                    source_text=item.get("source_text", ""),
                    summary=item.get("summary", ""),
                    status=ForeshadowStatus.ACTIVE,
                    current_probability=0.02,
                    next_eligible_chapter=chapter + MINIMUM_AGE,
                )
            )
            changed = True
        if changed:
            self._foreshadow_store.save_records(records)

    async def _extract_information(
        self,
        novel_id: str,
        chapter: int,
        prose_text: str,
        state: ChapterPipelineState,
    ) -> ChapterInformation | None:
        """Extract structured information from the committed prose."""
        # Check for existing (idempotent recovery)
        existing = self._info_store.load(novel_id, chapter)
        if existing is not None:
            return existing

        schema = self.get_schema(novel_id)
        if schema is None or not schema.fields:
            return None

        data = await extract_information(
            novel_id=novel_id,
            chapter_number=chapter,
            prose_text=prose_text,
            schema=schema,
        )

        info = ChapterInformation(
            novel_id=novel_id,
            chapter_number=chapter,
            schema_revision=schema.revision,
            data=data,
        )
        return self._info_store.save(info)

    async def _integrate_memory(
        self,
        novel_id: str,
        chapter: int,
        information: ChapterInformation | None,
        state: ChapterPipelineState,
    ) -> None:
        """Integrate information into ChromaDB (derived retrieval only)."""
        # Check for existing integration record
        existing = self._integration_store.load(novel_id, chapter)
        if existing is not None and existing.status == "committed":
            return  # Already integrated

        if information is None:
            return

        schema = self.get_schema(novel_id)
        if schema is None:
            return

        # Run Integration LLM to create memory documents
        documents = await integrate_memory(
            novel_id=novel_id,
            chapter_number=chapter,
            information=information,
            schema=schema,
        )

        # Upsert to ChromaDB
        doc_ids = await self._chroma.upsert_documents(
            novel_id=novel_id,
            chapter=chapter,
            schema_revision=schema.revision,
            documents=documents,
        )

        # Record integration
        record = MemoryIntegrationRecord(
            novel_id=novel_id,
            chapter_number=chapter,
            schema_revision=schema.revision,
            document_ids=doc_ids,
            document_count=len(doc_ids),
            status="committed",
        )
        self._integration_store.save(record)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _transition(
        self,
        state: ChapterPipelineState,
        phase: ChapterPipelinePhase,
        **updates: Any,
    ) -> ChapterPipelineState:
        """Transition pipeline state and persist."""
        updated = state.model_copy(update={"phase": phase, **updates})
        return self._pipeline_store.save(updated)

    def _load_authorities(self, novel_id: str) -> _Authorities:
        """Read every authority the confirmation freeze is measured against."""

        outline = self._outline_store.load() if self._outline_store.exists() else None
        return _Authorities(
            bible=self._bible_store.load(),
            canon=self._canon_store.load(),
            threads=self._thread_store.load(),
            memories=self._memory_store.load(),
            outline=outline,
            outline_revision=outline.revision if outline is not None else 0,
            style_revision=self._style_revision(),
            schema_revision=self._schema_revision(novel_id),
        )

    def _style_revision(self) -> int:
        from story.production_persistence import ActiveStyleStore

        store = ActiveStyleStore(
            self._data_dir,
            lambda: (_ for _ in ()).throw(KeyError("active_style")),
        )
        if not store.exists():
            return 0
        binding = store.load()
        if not binding.style_profile_id:
            return 0
        return int(binding.profile_revision)

    def _schema_revision(self, novel_id: str) -> int:
        schema = self._schema_store.load(novel_id)
        return schema.revision if schema is not None else 0

    def _assert_frozen(
        self,
        novel_id: str,
        chapter: int,
        confirmation: ChapterConfirmation,
        authorities: _Authorities,
    ) -> None:
        """Fail closed when any authority moved since confirmation."""

        synopsis = self._synopsis_store.load(novel_id, chapter)
        current = AuthorityRevisions(
            synopsis_revision=synopsis.revision if synopsis else 0,
            story_bible_revision=authorities.bible.revision,
            canon_revision=authorities.canon.revision,
            story_thread_revision=authorities.threads.revision,
            memory_revision=authorities.memories.revision,
            outline_revision=authorities.outline_revision,
            style_revision=authorities.style_revision,
            information_schema_revision=authorities.schema_revision,
        )
        drift = confirmation.revisions().drift(current)
        if drift:
            raise ConfirmationStaleError(
                f"第 {chapter} 章确认已过期，拒绝使用未确认的版本生成："
                + "；".join(drift)
                + "；请重新确认本章"
            )

    def get_pipeline_state(self, novel_id: str, chapter: int) -> ChapterPipelineState | None:
        return self._pipeline_store.load(novel_id, chapter)

    def get_current_chapter(self, novel_id: str) -> int:
        return self._pipeline_store.get_current_chapter(novel_id)

    def committed_chapter_prose(
        self,
        novel_id: str,
        chapter: int,
        author_service: AuthorGenerationService,
    ) -> str:
        """Return the officially committed manuscript for a completed chapter."""

        state = self._pipeline_store.load(novel_id, chapter)
        if state is None or not state.committed_manuscript:
            return ""
        section = author_service.sections.get_by_id(state.committed_section_id)
        return section.content if section is not None else ""
