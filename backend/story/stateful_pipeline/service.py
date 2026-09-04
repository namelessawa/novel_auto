"""Chapter generation pipeline orchestrator.

Coordinates the full stateful pipeline:
  1. User confirmation gate
  2. Context preparation (Transfer LLM for ch >= 3)
  3. Novel LLM writing
  4. Foreshadow extraction
  5. Information extraction
  6. Memory integration (ChromaDB)
  7. Commit

Key principles:
  - Programs handle deterministic rules
  - LLMs handle semantic work
  - All random decisions persisted for recovery
  - User confirmation required before each chapter
"""

from __future__ import annotations

from typing import Any

from story.models import (
    CanonicalState,
    StoryBible,
)
from story.stateful_pipeline.chroma_repository import ChromaMemoryRepository
from story.stateful_pipeline.foreshadow_selection import (
    ForeshadowSelectionService,
)
from story.stateful_pipeline.llm_roles import (
    build_transfer_context,
    extract_foreshadows,
    extract_information,
    generate_information_schema,
    generate_synopsis,
    integrate_memory,
)
from story.stateful_pipeline.models import (
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
    TransferContext,
)
from story.stateful_pipeline.persistence import (
    ChapterInformationStore,
    ForeshadowStore,
    MemoryIntegrationStore,
    PipelineStateStore,
    SynopsisStore,
    TransferContextStore,
)


class PipelineError(RuntimeError):
    """Raised when pipeline encounters an unrecoverable error."""


class ConfirmationRequiredError(PipelineError):
    """Raised when generation is attempted without user confirmation."""


class StatefulPipelineService:
    """Orchestrates the full chapter generation pipeline.

    This service coordinates:
      - User confirmation gates
      - Foreshadow selection (deterministic)
      - LLM role invocations
      - ChromaDB integration
      - State persistence and recovery
    """

    def __init__(self, data_dir: str, chroma_repo: ChromaMemoryRepository | None = None):
        self._data_dir = data_dir
        self._chroma = chroma_repo or ChromaMemoryRepository()
        self._selection_service = ForeshadowSelectionService()

        # Persistence stores
        self._synopsis_store = SynopsisStore(data_dir)
        self._foreshadow_store = ForeshadowStore(data_dir)
        self._info_store = ChapterInformationStore(data_dir)
        self._transfer_store = TransferContextStore(data_dir)
        self._pipeline_store = PipelineStateStore(data_dir)
        self._integration_store = MemoryIntegrationStore(data_dir)

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
        bible_summary = self._summarize_bible(story_bible)

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
        from story.stateful_pipeline.persistence import InformationSchemaStore
        store = InformationSchemaStore(self._data_dir)
        return store.load(novel_id)

    async def ensure_schema(
        self,
        novel_id: str,
        story_bible: StoryBible,
        genre: str,
        synopses: list[ChapterSynopsis],
    ) -> InformationSchema:
        """Get or auto-generate information schema."""
        from story.stateful_pipeline.persistence import InformationSchemaStore
        store = InformationSchemaStore(self._data_dir)

        existing = store.load(novel_id)
        if existing is not None:
            return existing

        # Auto-generate schema
        bible_summary = self._summarize_bible(story_bible)
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
        return store.save(schema)

    def update_schema(
        self,
        novel_id: str,
        fields: list[dict[str, Any]],
    ) -> InformationSchema:
        """Update schema fields (user edit). Creates new revision."""
        from story.stateful_pipeline.persistence import InformationSchemaStore
        store = InformationSchemaStore(self._data_dir)

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

        existing = store.load(novel_id)
        revision = (existing.revision + 1) if existing else 1

        schema = InformationSchema(
            novel_id=novel_id,
            revision=revision,
            fields=field_objects,
            source="user_defined",
        )
        return store.save(schema)

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
        bible: StoryBible,
        canon: CanonicalState,
        style_revision: int,
    ) -> ChapterConfirmation:
        """Bind user confirmation to current revisions.

        Creates a frozen snapshot that generation must respect.
        """
        synopsis = self.get_synopsis(novel_id, chapter)
        synopsis_revision = synopsis.revision if synopsis else 0

        schema = self.get_schema(novel_id)
        schema_revision = schema.revision if schema else 0

        confirmation = ChapterConfirmation(
            novel_id=novel_id,
            chapter_number=chapter,
            synopsis_revision=synopsis_revision,
            story_bible_revision=bible.revision,
            canon_revision=canon.revision,
            style_revision=style_revision,
            information_schema_revision=schema_revision,
        )

        # Initialize pipeline state
        state = ChapterPipelineState(
            novel_id=novel_id,
            chapter_number=chapter,
            phase=ChapterPipelinePhase.AWAITING_CONFIRMATION,
            synopsis_revision=synopsis_revision,
            story_bible_revision=bible.revision,
            canon_revision=canon.revision,
            style_revision=style_revision,
            information_schema_revision=schema_revision,
            generation_preference=preference,
        )
        self._pipeline_store.save(state)

        return confirmation

    # ------------------------------------------------------------------
    # Pipeline Execution
    # ------------------------------------------------------------------

    async def run_chapter_pipeline(
        self,
        novel_id: str,
        chapter: int,
        confirmation: ChapterConfirmation,
        bible: StoryBible,
        canon: CanonicalState,
        style_prefix: str,
        chapter_goal: str,
    ) -> ChapterPipelineState:
        """Execute the full chapter generation pipeline.

        Phases:
          preparing_context → writing → extracting_foreshadows →
          extracting_information → integrating_memory → committing → completed
        """
        state = self._pipeline_store.load(novel_id, chapter)
        if state is None:
            state = ChapterPipelineState(
                novel_id=novel_id,
                chapter_number=chapter,
            )

        # Check confirmation
        if state.phase == ChapterPipelinePhase.AWAITING_CONFIRMATION:
            if confirmation is None:
                raise ConfirmationRequiredError(
                    f"Chapter {chapter} requires user confirmation before generation"
                )
            # Verify confirmation matches current state
            self._validate_confirmation(confirmation, bible, canon)

        # Phase 1: Prepare context
        state = self._transition(state, ChapterPipelinePhase.PREPARING_CONTEXT)

        # Roll new-foreshadow count + select eligible foreshadows.
        # Persisted as a receipt BEFORE writing so retry never re-rolls.
        receipt = self._prepare_foreshadow_decisions(novel_id, chapter, state)

        transfer_context = None
        if chapter >= 3:
            transfer_context = await self._prepare_transfer_context(
                novel_id, chapter, state, receipt
            )

        # Phase 2: Write (uses existing Writer mechanism)
        state = self._transition(state, ChapterPipelinePhase.WRITING)
        prose_text = await self._write_chapter(
            novel_id=novel_id,
            chapter=chapter,
            bible=bible,
            canon=canon,
            style_prefix=style_prefix,
            chapter_goal=chapter_goal,
            synopsis=self.get_synopsis(novel_id, chapter),
            transfer_context=transfer_context,
        )

        # Phase 3: Extract foreshadows
        state = self._transition(state, ChapterPipelinePhase.EXTRACTING_FORESHADOWS)
        await self._extract_foreshadows(novel_id, chapter, prose_text, state)

        # Phase 4: Extract information
        state = self._transition(state, ChapterPipelinePhase.EXTRACTING_INFORMATION)
        information = await self._extract_information(novel_id, chapter, prose_text, state)

        # Phase 5: Integrate memory
        state = self._transition(state, ChapterPipelinePhase.INTEGRATING_MEMORY)
        await self._integrate_memory(novel_id, chapter, information, state)

        # Phase 6: Commit
        state = self._transition(state, ChapterPipelinePhase.COMMITTING)

        # Phase 7: Complete
        state = self._transition(state, ChapterPipelinePhase.COMPLETED)
        return state

    # ------------------------------------------------------------------
    # Internal Phase Implementations
    # ------------------------------------------------------------------

    async def _prepare_transfer_context(
        self,
        novel_id: str,
        chapter: int,
        state: ChapterPipelineState,
        receipt: ForeshadowSelectionReceipt | None = None,
    ) -> TransferContext | None:
        """Run Transfer LLM for chapters >= 3."""
        # Check for cached transfer context (idempotent recovery)
        cached = self._transfer_store.load(novel_id, chapter)
        if cached is not None:
            return cached

        # Get recent chapter informations (up to 3)
        recent_infos = self._info_store.load_recent(novel_id, chapter, count=3)

        # Get selected foreshadow (from receipt)
        if receipt is None:
            receipt = self._foreshadow_store.load_receipt(novel_id, chapter)
        selected_foreshadow = None
        if receipt and receipt.collision_winner and not receipt.discarded:
            records = self._foreshadow_store.load_records(novel_id)
            selected_foreshadow = next(
                (f for f in records if f.id == receipt.collision_winner), None
            )

        # Get synopsis
        synopsis = self.get_synopsis(novel_id, chapter)
        synopsis_text = synopsis.synopsis if synopsis else ""

        transfer_ctx = await build_transfer_context(
            novel_id=novel_id,
            target_chapter=chapter,
            recent_informations=recent_infos,
            selected_foreshadow=selected_foreshadow,
            chapter_synopsis=synopsis_text,
        )

        self._transfer_store.save(transfer_ctx)
        return transfer_ctx

    def _prepare_foreshadow_decisions(
        self,
        novel_id: str,
        chapter: int,
        state: ChapterPipelineState,
    ) -> ForeshadowSelectionReceipt | None:
        """Roll new-foreshadow count and select eligible foreshadows.

        Runs during preparing_context. All random decisions are persisted
        in a receipt so retry/restart never re-rolls (spec §17).

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

    async def _write_chapter(
        self,
        novel_id: str,
        chapter: int,
        bible: StoryBible,
        canon: CanonicalState,
        style_prefix: str,
        chapter_goal: str,
        synopsis: ChapterSynopsis | None,
        transfer_context: TransferContext | None,
    ) -> str:
        """Write chapter prose using the simplified writer with pacing mode.

        The simplified writer outputs plain prose based on:
          - StyleProfile.writer_prompt_prefix (style_prefix)
          - Chapter synopsis
          - Pacing mode (flat/conflict/climax)
          - TransferContext (from chapter >= 3)
        """
        from story.stateful_pipeline.llm_roles import write_chapter_simplified
        from story.stateful_pipeline.pacing import PacingModeSelector
        from story.stateful_pipeline.persistence import PacingStore

        # Get or create pacing state
        pacing_store = PacingStore(self._data_dir)
        pacing_state = pacing_store.load_state(novel_id)
        pacing_selector = PacingModeSelector()

        # Check for existing pacing receipt (idempotent recovery)
        pacing_receipt = pacing_store.load_receipt(novel_id, chapter)
        pacing_receipt = pacing_selector.select_mode(
            novel_id=novel_id,
            chapter=chapter,
            state=pacing_state,
            existing_receipt=pacing_receipt,
        )
        pacing_store.save_state(pacing_state)
        pacing_store.save_receipt(pacing_receipt)

        # Determine the pacing mode instruction
        pacing_mode = pacing_receipt.selected_mode.value
        if pacing_mode == "conflict" and pacing_receipt.resolve_in_chapter:
            pacing_mode = "conflict_resolve"

        # Build synopsis text
        synopsis_text = synopsis.synopsis if synopsis and synopsis.synopsis else chapter_goal or "推进故事发展"

        # Build transfer context text
        transfer_text = ""
        if transfer_context:
            parts = []
            if transfer_context.recent_context:
                parts.append(f"近期上下文：{transfer_context.recent_context}")
            if transfer_context.foreshadow_to_consider:
                parts.append(f"需融入的伏笔：{transfer_context.foreshadow_to_consider}")
            if transfer_context.continuity_constraints:
                parts.append("连续性约束：" + "；".join(transfer_context.continuity_constraints))
            transfer_text = "\n".join(parts)

        try:
            prose = await write_chapter_simplified(
                novel_id=novel_id,
                chapter_number=chapter,
                synopsis=synopsis_text,
                style_prefix=style_prefix,
                pacing_mode=pacing_mode,
                transfer_context=transfer_text,
            )

            # If the pacing mode resolved an open conflict, mark it resolved
            if pacing_mode in ("conflict_resolve", "climax"):
                pacing_selector.resolve_open_conflict(pacing_state, chapter)
                pacing_store.save_state(pacing_state)

            return prose
        except Exception as exc:
            raise PipelineError(f"Chapter writing failed: {exc}") from exc

    async def _extract_foreshadows(
        self,
        novel_id: str,
        chapter: int,
        prose_text: str,
        state: ChapterPipelineState,
    ) -> None:
        """Extract new foreshadows from the written prose.

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
        """Extract structured information from prose."""
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
        """Integrate information into ChromaDB."""
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
    ) -> ChapterPipelineState:
        """Transition pipeline state and persist."""
        updated = state.model_copy(update={"phase": phase})
        return self._pipeline_store.save(updated)

    def _validate_confirmation(
        self,
        confirmation: ChapterConfirmation,
        bible: StoryBible,
        canon: CanonicalState,
    ) -> None:
        """Verify confirmation matches current revisions."""
        if confirmation.story_bible_revision != bible.revision:
            raise PipelineError(
                f"StoryBible revision changed: confirmed {confirmation.story_bible_revision}, "
                f"current {bible.revision}"
            )
        if confirmation.canon_revision != canon.revision:
            raise PipelineError(
                f"CanonicalState revision changed: confirmed {confirmation.canon_revision}, "
                f"current {canon.revision}"
            )

    def _summarize_bible(self, bible: StoryBible) -> str:
        """Create a compact summary of StoryBible for LLM prompts."""
        parts = []
        if hasattr(bible, "title"):
            parts.append(f"标题：{bible.title}")
        if hasattr(bible, "genre"):
            parts.append(f"类型：{bible.genre}")
        if hasattr(bible, "core_premise"):
            parts.append(f"核心设定：{bible.core_premise}")
        if hasattr(bible, "main_conflict"):
            parts.append(f"主要冲突：{bible.main_conflict}")
        return "\n".join(parts) if parts else str(bible)

    def get_pipeline_state(self, novel_id: str, chapter: int) -> ChapterPipelineState | None:
        return self._pipeline_store.load(novel_id, chapter)

    def get_current_chapter(self, novel_id: str) -> int:
        return self._pipeline_store.get_current_chapter(novel_id)
