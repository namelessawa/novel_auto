"""Domain models for the stateful chapter generation pipeline.

These models support the multi-LLM pipeline:
  Synopsis → Novel Writer → Foreshadow → Information → Integration → Transfer

Key principles:
  - Programs handle deterministic rules (probabilities, state machines)
  - LLMs handle semantic work (writing, extraction, summarization)
  - All random decisions are persisted for recovery/idempotency
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# Chapter Synopsis
# ---------------------------------------------------------------------------


class ChapterSynopsis(PipelineModel):
    """User-editable synopsis for a chapter.

    The first two chapters use dedicated synopsis; later chapters
    fall back to the existing BookOutline/chapter goal mechanism.
    """

    novel_id: str
    chapter_number: int = Field(ge=1)
    title: str = ""
    synopsis: str = ""
    revision: int = Field(default=1, ge=1)
    frozen_at: str | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    def freeze(self) -> ChapterSynopsis:
        """Return a copy with frozen_at set (for generation binding)."""
        return self.model_copy(update={"frozen_at": utc_now()})

    @property
    def is_frozen(self) -> bool:
        return self.frozen_at is not None


# ---------------------------------------------------------------------------
# Information Schema
# ---------------------------------------------------------------------------


class InformationField(PipelineModel):
    """A single field in the information collection schema."""

    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    order: int = Field(default=0, ge=0)


class InformationSchema(PipelineModel):
    """User-configurable schema for information extraction.

    All chapters in a novel use the same schema revision unless
    explicitly updated by the user.
    """

    novel_id: str
    revision: int = Field(default=1, ge=1)
    fields: list[InformationField] = Field(default_factory=list)
    source: Literal["user_defined", "auto_generated"] = "user_defined"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @property
    def field_keys(self) -> list[str]:
        return [f.key for f in sorted(self.fields, key=lambda f: f.order)]

    def validate_extraction_keys(self, keys: set[str]) -> list[str]:
        """Return keys in extraction that don't match schema."""
        allowed = set(self.field_keys)
        return sorted(keys - allowed)


# ---------------------------------------------------------------------------
# Chapter Information (LLM extraction output)
# ---------------------------------------------------------------------------


class ChapterInformation(PipelineModel):
    """Structured information extracted from a chapter by Information LLM."""

    novel_id: str
    chapter_number: int = Field(ge=1)
    schema_revision: int = Field(ge=1)
    data: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    source: Literal["llm_extracted", "reconstructed"] = "llm_extracted"
    created_at: str = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Foreshadow Records
# ---------------------------------------------------------------------------


class ForeshadowStatus(str, Enum):
    ACTIVE = "active"
    SELECTED = "selected"
    DISCARDED = "discarded"


class ForeshadowRecord(PipelineModel):
    """A foreshadow item extracted from a chapter.

    Lifecycle: active → selected (once chosen) → optionally discarded
    """

    id: str
    novel_id: str
    source_chapter: int = Field(ge=1)
    source_text: str = ""
    summary: str = ""
    status: ForeshadowStatus = ForeshadowStatus.ACTIVE
    selected_once: bool = False
    current_probability: float = Field(default=0.02, ge=0.0, le=1.0)
    next_eligible_chapter: int = Field(default=0, ge=0)
    created_at: str = Field(default_factory=utc_now)
    selected_chapter: int | None = None
    discarded: bool = False

    def age_at(self, chapter: int) -> int:
        return chapter - self.source_chapter

    def is_eligible(self, chapter: int) -> bool:
        """Check if this foreshadow can participate in selection at given chapter."""
        if self.selected_once:
            return False
        if self.status != ForeshadowStatus.ACTIVE:
            return False
        if chapter < self.next_eligible_chapter:
            return False
        if self.age_at(chapter) < 8:
            return False
        return True


# ---------------------------------------------------------------------------
# Foreshadow Selection State & Receipt
# ---------------------------------------------------------------------------


class ForeshadowSelectionState(PipelineModel):
    """Global state for the foreshadow selection mechanism."""

    novel_id: str
    consecutive_selection_count: int = Field(default=0, ge=0)
    discard_unlocked: bool = False
    last_selected_chapter: int | None = None
    updated_at: str = Field(default_factory=utc_now)


class ForeshadowMode(str, Enum):
    RANDOM = "random"
    FIXED = "fixed"


class ChapterGenerationPreference(PipelineModel):
    """User choices before generating a chapter."""

    novel_id: str
    chapter_number: int = Field(ge=1)
    foreshadow_mode: ForeshadowMode = ForeshadowMode.RANDOM
    foreshadow_fixed_count: int = Field(default=0, ge=0, le=2)
    confirmed_at: str | None = None
    created_at: str = Field(default_factory=utc_now)


class SelectionRollResult(PipelineModel):
    """Result of a single foreshadow's probability roll."""

    foreshadow_id: str
    probability: float
    roll_value: float
    hit: bool


class ForeshadowSelectionReceipt(PipelineModel):
    """Persisted receipt for all random decisions in a chapter.

    Ensures idempotent recovery: the same decisions are replayed
    on retry/restart without re-rolling.
    """

    novel_id: str
    chapter: int = Field(ge=1)
    new_foreshadow_count: int = Field(default=0, ge=0, le=2)
    new_foreshadow_roll: float | None = None
    eligible_foreshadow_ids: list[str] = Field(default_factory=list)
    roll_results: list[SelectionRollResult] = Field(default_factory=list)
    collision_candidates: list[str] = Field(default_factory=list)
    collision_winner: str | None = None
    collision_roll: float | None = None
    discard_roll: float | None = None
    discarded: bool = False
    cooldown_applied: list[str] = Field(default_factory=list)
    probability_increments: dict[str, float] = Field(default_factory=dict)
    applied_to_records: bool = False
    created_at: str = Field(default_factory=utc_now)

    @property
    def selected_foreshadow_id(self) -> str | None:
        return self.collision_winner


# ---------------------------------------------------------------------------
# Transfer Context
# ---------------------------------------------------------------------------


class TransferContext(PipelineModel):
    """Output of the Transfer LLM: structured context for the Novel LLM."""

    novel_id: str
    target_chapter: int = Field(ge=1)
    recent_context: str = ""
    foreshadow_to_consider: str = ""
    continuity_constraints: list[str] = Field(default_factory=list)
    important_entities: list[str] = Field(default_factory=list)
    source_chapters: list[int] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Memory Integration Record
# ---------------------------------------------------------------------------


class MemoryIntegrationRecord(PipelineModel):
    """Record of what was written to ChromaDB for a chapter."""

    novel_id: str
    chapter_number: int = Field(ge=1)
    schema_revision: int = Field(ge=1)
    document_ids: list[str] = Field(default_factory=list)
    document_count: int = Field(default=0, ge=0)
    status: Literal["pending", "committed", "failed"] = "pending"
    created_at: str = Field(default_factory=utc_now)
    committed_at: str | None = None


# ---------------------------------------------------------------------------
# Chapter Pipeline State
# ---------------------------------------------------------------------------


class ChapterPipelinePhase(str, Enum):
    AWAITING_CONFIRMATION = "awaiting_user_confirmation"
    CONFIRMED = "confirmed"
    PREPARING_CONTEXT = "preparing_context"
    WRITING = "writing"
    EXTRACTING_FORESHADOWS = "extracting_foreshadows"
    EXTRACTING_INFORMATION = "extracting_information"
    INTEGRATING_MEMORY = "integrating_memory"
    COMMITTING = "committing"
    COMPLETED = "chapter_completed"
    FAILED = "failed"


class AuthorityRevisions(PipelineModel):
    """Every authority revision the Author production chain reads.

    Frozen at confirmation and re-checked before generation so a chapter can
    never silently bind to an authority the user edited afterwards.
    """

    synopsis_revision: int = Field(ge=0)
    story_bible_revision: int = Field(ge=1)
    canon_revision: int = Field(ge=1)
    story_thread_revision: int = Field(ge=1)
    memory_revision: int = Field(ge=1)
    outline_revision: int = Field(ge=1)
    style_revision: int = Field(ge=0)
    information_schema_revision: int = Field(ge=0)

    def drift(self, current: "AuthorityRevisions") -> list[str]:
        """Return every authority that moved since confirmation."""

        drifted = []
        for name in type(self).model_fields:
            frozen = getattr(self, name)
            live = getattr(current, name)
            if frozen != live:
                drifted.append(f"{name}: confirmed {frozen}, current {live}")
        return drifted


class ChapterPipelineState(PipelineModel):
    """State machine tracking the current phase of chapter generation.

    The revision fields plus ``synopsis_title``/``synopsis_text`` are the
    immutable confirmation snapshot: generation binds to them and fails closed
    when a live authority has moved on, never silently reading the new value.
    ``committed_*`` fields are the Author commit evidence that makes
    ``COMPLETED`` meaningful.
    """

    novel_id: str
    chapter_number: int = Field(ge=1)
    phase: ChapterPipelinePhase = ChapterPipelinePhase.AWAITING_CONFIRMATION
    attempt: int = Field(default=1, ge=1)
    synopsis_revision: int | None = None
    synopsis_title: str = ""
    synopsis_text: str = ""
    story_bible_revision: int | None = None
    canon_revision: int | None = None
    story_thread_revision: int | None = None
    memory_revision: int | None = None
    outline_revision: int | None = None
    style_revision: int | None = None
    information_schema_revision: int | None = None
    generation_preference: ChapterGenerationPreference | None = None
    selection_receipt: ForeshadowSelectionReceipt | None = None
    transfer_context: TransferContext | None = None
    author_transaction_id: str = ""
    committed_section_id: str = ""
    committed_char_count: int = Field(default=0, ge=0)
    committed_canonical_revision: int | None = None
    committed_at: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    updated_at: str = Field(default_factory=utc_now)

    @property
    def is_terminal(self) -> bool:
        return self.phase in (
            ChapterPipelinePhase.COMPLETED,
            ChapterPipelinePhase.FAILED,
        )

    @property
    def is_confirmed(self) -> bool:
        return self.phase is not ChapterPipelinePhase.AWAITING_CONFIRMATION and (
            self.story_bible_revision is not None
        )

    @property
    def committed_manuscript(self) -> bool:
        """True only when a real Author commit was recorded for this chapter."""

        return bool(
            self.phase == ChapterPipelinePhase.COMPLETED
            and self.committed_section_id
            and self.author_transaction_id
            and self.committed_char_count > 0
            and (self.committed_canonical_revision or 0) > 0
        )

    def frozen_confirmation(self) -> ChapterConfirmation | None:
        """Rebuild the immutable confirmation binding, or None when absent."""

        revisions = (
            self.synopsis_revision,
            self.story_bible_revision,
            self.canon_revision,
            self.story_thread_revision,
            self.memory_revision,
            self.outline_revision,
            self.style_revision,
            self.information_schema_revision,
        )
        if any(value is None for value in revisions):
            return None
        return ChapterConfirmation(
            novel_id=self.novel_id,
            chapter_number=self.chapter_number,
            synopsis_revision=self.synopsis_revision or 0,
            synopsis_title=self.synopsis_title,
            synopsis_text=self.synopsis_text,
            story_bible_revision=self.story_bible_revision or 0,
            canon_revision=self.canon_revision or 0,
            story_thread_revision=self.story_thread_revision or 0,
            memory_revision=self.memory_revision or 0,
            outline_revision=self.outline_revision or 0,
            style_revision=self.style_revision or 0,
            information_schema_revision=self.information_schema_revision or 0,
        )


# ---------------------------------------------------------------------------
# Confirmation Binding
# ---------------------------------------------------------------------------


class ChapterConfirmation(PipelineModel):
    """Immutable binding snapshot taken when the user confirms a chapter.

    Every authority revision the Author production chain reads is frozen here,
    together with the synopsis content itself (the synopsis store keeps only the
    newest revision, so the text must travel with the confirmation).
    """

    novel_id: str
    chapter_number: int = Field(ge=1)
    synopsis_revision: int = Field(ge=0)
    synopsis_title: str = ""
    synopsis_text: str = ""
    story_bible_revision: int = Field(ge=1)
    canon_revision: int = Field(ge=1)
    story_thread_revision: int = Field(ge=1)
    memory_revision: int = Field(ge=1)
    outline_revision: int = Field(ge=1)
    style_revision: int = Field(ge=0)
    information_schema_revision: int = Field(ge=0)
    confirmed_at: str = Field(default_factory=utc_now)

    def revisions(self) -> AuthorityRevisions:
        return AuthorityRevisions(
            synopsis_revision=self.synopsis_revision,
            story_bible_revision=self.story_bible_revision,
            canon_revision=self.canon_revision,
            story_thread_revision=self.story_thread_revision,
            memory_revision=self.memory_revision,
            outline_revision=self.outline_revision,
            style_revision=self.style_revision,
            information_schema_revision=self.information_schema_revision,
        )
