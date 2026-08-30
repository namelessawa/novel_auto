"""Persistent contracts for whole-book author production.

The existing :mod:`story.models` contracts remain the authority for one
section transaction.  This module adds the durable, book-level planning and
job contracts which sit above those transactions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from story.narrative_contract import (
    ForbiddenAddition,
    RequiredEndState,
    RequiredEvent,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def non_whitespace_char_count(text: str) -> int:
    """Return the canonical Chinese manuscript length metric."""

    return sum(1 for char in text if not char.isspace())


# A descriptive alias is convenient at API/report call sites.
count_non_whitespace_chars = non_whitespace_char_count


class ProductionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ProductionStatus = Literal[
    "draft",
    "outline_ready",
    "ready",
    "queued",
    "running",
    "paused",
    "failed",
    "cancelled",
    "completed",
]


class NovelProductionSpec(ProductionModel):
    """User-owned whole-book scale and creative production contract."""

    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    title: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    genre: str = ""
    theme: str = Field(min_length=1)
    central_question: str = ""
    target_total_chars: int = Field(default=300_000, ge=1_000)
    volume_count: int = Field(default=5, ge=1, le=1_000)
    chapter_count: int = Field(default=100, ge=1, le=100_000)
    target_chapter_chars: int = Field(default=3_000, ge=200, le=1_000_000)
    accepted_chapter_min_chars: int = Field(default=2_700, ge=200)
    accepted_chapter_max_chars: int = Field(default=3_300, ge=200)
    section_target_chars: int = Field(default=1_500, ge=200, le=100_000)
    generation_language: str = Field(default="zh-CN", min_length=1)
    ending_direction: str = ""
    production_status: ProductionStatus = "draft"
    active_style_profile_id: str = "preset_literary"
    char_count_policy: Literal["non_whitespace"] = "non_whitespace"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_scale(self) -> "NovelProductionSpec":
        if self.volume_count > self.chapter_count:
            raise ValueError("volume_count cannot exceed chapter_count")
        if self.accepted_chapter_min_chars > self.target_chapter_chars:
            raise ValueError(
                "accepted_chapter_min_chars cannot exceed target_chapter_chars"
            )
        if self.target_chapter_chars > self.accepted_chapter_max_chars:
            raise ValueError(
                "target_chapter_chars cannot exceed accepted_chapter_max_chars"
            )
        if self.section_target_chars > self.accepted_chapter_max_chars:
            raise ValueError(
                "section_target_chars cannot exceed accepted chapter maximum"
            )
        minimum_total = self.chapter_count * self.accepted_chapter_min_chars
        maximum_total = self.chapter_count * self.accepted_chapter_max_chars
        if not minimum_total <= self.target_total_chars <= maximum_total:
            raise ValueError(
                "target_total_chars must fit chapter_count and accepted chapter range"
            )
        return self


class NovelProductionSpecUpdate(ProductionModel):
    """Optimistic-concurrency patch for :class:`NovelProductionSpec`."""

    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1)
    premise: str | None = Field(default=None, min_length=1)
    genre: str | None = None
    theme: str | None = Field(default=None, min_length=1)
    central_question: str | None = None
    target_total_chars: int | None = Field(default=None, ge=1_000)
    volume_count: int | None = Field(default=None, ge=1, le=1_000)
    chapter_count: int | None = Field(default=None, ge=1, le=100_000)
    target_chapter_chars: int | None = Field(
        default=None, ge=200, le=1_000_000
    )
    accepted_chapter_min_chars: int | None = Field(default=None, ge=200)
    accepted_chapter_max_chars: int | None = Field(default=None, ge=200)
    section_target_chars: int | None = Field(
        default=None, ge=200, le=100_000
    )
    generation_language: str | None = Field(default=None, min_length=1)
    ending_direction: str | None = None
    production_status: ProductionStatus | None = None
    active_style_profile_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate_supplied_range(self) -> "NovelProductionSpecUpdate":
        minimum = self.accepted_chapter_min_chars
        target = self.target_chapter_chars
        maximum = self.accepted_chapter_max_chars
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(
                "accepted_chapter_min_chars cannot exceed "
                "accepted_chapter_max_chars"
            )
        if minimum is not None and target is not None and minimum > target:
            raise ValueError(
                "accepted_chapter_min_chars cannot exceed target_chapter_chars"
            )
        if target is not None and maximum is not None and target > maximum:
            raise ValueError(
                "target_chapter_chars cannot exceed accepted_chapter_max_chars"
            )
        return self


class VolumeOutline(ProductionModel):
    id: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    opening_state: str = ""
    closing_state: str = ""
    target_chapters: int = Field(ge=1)
    target_chars: int = Field(ge=200)


ChapterOutlineStatus = Literal[
    "draft",
    "ready",
    "generating",
    "committed",
    "failed",
    "cancelled",
]


class ChapterOutline(ProductionModel):
    id: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    volume_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    viewpoint_character_id: str = ""
    location_id: str = ""
    involved_characters: list[str] = Field(default_factory=list)
    target_threads: list[str] = Field(default_factory=list)
    required_events: list[RequiredEvent] = Field(default_factory=list)
    required_end_states: list[RequiredEndState] = Field(default_factory=list)
    prohibited_additions: list[ForbiddenAddition] = Field(default_factory=list)
    target_chars: int = Field(ge=200)
    status: ChapterOutlineStatus = "draft"
    committed_section_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "involved_characters",
        "target_threads",
        "committed_section_ids",
    )
    @classmethod
    def _unique_nonempty_strings(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


BookOutlineStatus = Literal["draft", "ready", "locked", "completed"]


class BookOutline(ProductionModel):
    """Strict deterministic whole-book structure.

    An empty ``draft`` is allowed for migration.  As soon as any outline
    content exists, volume and chapter numbering and budgets must close.
    """

    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    progress_revision: int = Field(default=1, ge=1)
    logline: str = ""
    global_arc: str = ""
    volumes: list[VolumeOutline] = Field(default_factory=list)
    chapters: list[ChapterOutline] = Field(default_factory=list)
    ending_target: str = ""
    major_turning_points: list[str] = Field(default_factory=list)
    central_conflict_progression: list[str] = Field(default_factory=list)
    thread_schedule: dict[str, list[str]] = Field(default_factory=dict)
    character_arc_schedule: dict[str, list[str]] = Field(default_factory=dict)
    status: BookOutlineStatus = "draft"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator(
        "major_turning_points",
        "central_conflict_progression",
    )
    @classmethod
    def _unique_nonempty_strings(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @model_validator(mode="after")
    def _validate_structure(self) -> "BookOutline":
        if not self.volumes and not self.chapters:
            if self.status != "draft":
                raise ValueError("only a draft BookOutline may be empty")
            return self
        if not self.volumes or not self.chapters:
            raise ValueError("volumes and chapters must both be populated")

        volume_ids = [volume.id for volume in self.volumes]
        chapter_ids = [chapter.id for chapter in self.chapters]
        if len(volume_ids) != len(set(volume_ids)):
            raise ValueError("volume IDs must be unique")
        if len(chapter_ids) != len(set(chapter_ids)):
            raise ValueError("chapter IDs must be unique")

        expected_volume_ordinals = list(range(1, len(self.volumes) + 1))
        actual_volume_ordinals = [
            volume.ordinal for volume in sorted(self.volumes, key=lambda item: item.ordinal)
        ]
        if actual_volume_ordinals != expected_volume_ordinals:
            raise ValueError("volume ordinals must be contiguous and start at 1")

        expected_chapter_ordinals = list(range(1, len(self.chapters) + 1))
        ordered_chapters = sorted(self.chapters, key=lambda item: item.ordinal)
        actual_chapter_ordinals = [chapter.ordinal for chapter in ordered_chapters]
        if actual_chapter_ordinals != expected_chapter_ordinals:
            raise ValueError("chapter ordinals must be contiguous and start at 1")

        known_volume_ids = set(volume_ids)
        unknown = sorted(
            {
                chapter.volume_id
                for chapter in self.chapters
                if chapter.volume_id not in known_volume_ids
            }
        )
        if unknown:
            raise ValueError(f"chapters reference unknown volume IDs: {unknown}")

        volume_order = {volume.id: volume.ordinal for volume in self.volumes}
        assigned_orders = [
            volume_order[chapter.volume_id] for chapter in ordered_chapters
        ]
        if assigned_orders != sorted(assigned_orders):
            raise ValueError("chapters assigned to a volume must form one ordered block")

        for volume in self.volumes:
            owned = [
                chapter
                for chapter in self.chapters
                if chapter.volume_id == volume.id
            ]
            if len(owned) != volume.target_chapters:
                raise ValueError(
                    f"volume {volume.id!r} target_chapters does not match chapters"
                )
            if sum(chapter.target_chars for chapter in owned) != volume.target_chars:
                raise ValueError(
                    f"volume {volume.id!r} target_chars does not match chapter budget"
                )
        return self

    @property
    def target_chars(self) -> int:
        return sum(chapter.target_chars for chapter in self.chapters)

    def validation_errors_for(
        self, spec: NovelProductionSpec
    ) -> list[str]:
        """Return deterministic cross-contract errors without mutating either model."""

        errors: list[str] = []
        if len(self.volumes) != spec.volume_count:
            errors.append("outline volume count does not match production spec")
        if len(self.chapters) != spec.chapter_count:
            errors.append("outline chapter count does not match production spec")
        if self.target_chars != spec.target_total_chars:
            errors.append("outline character budget does not match production spec")
        for chapter in self.chapters:
            if not (
                spec.accepted_chapter_min_chars
                <= chapter.target_chars
                <= spec.accepted_chapter_max_chars
            ):
                errors.append(
                    f"chapter {chapter.id!r} target_chars is outside accepted range"
                )
        return errors


class BookOutlineUpdate(ProductionModel):
    expected_revision: int = Field(ge=1)
    logline: str | None = None
    global_arc: str | None = None
    volumes: list[VolumeOutline] | None = None
    chapters: list[ChapterOutline] | None = None
    ending_target: str | None = None
    major_turning_points: list[str] | None = None
    central_conflict_progression: list[str] | None = None
    thread_schedule: dict[str, list[str]] | None = None
    character_arc_schedule: dict[str, list[str]] | None = None
    status: BookOutlineStatus | None = None


def _normalise_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    return list(
        dict.fromkeys(
            str(item).strip() for item in values if str(item).strip()
        )
    )


class StyleProfile(ProductionModel):
    """Versioned expression-only writing contract.

    ``optional_user_sample`` is retained as user data but deliberately omitted
    from both the prompt contract and prompt hash.  Generated prose therefore
    receives derived features, never sample sentences.
    """

    schema_version: int = Field(default=1, ge=1)
    id: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)
    name: str = Field(min_length=1)
    base_preset_key: str = ""
    description: str = ""
    narrative_voice: str = ""
    viewpoint: str = ""
    tense: str = ""
    sentence_length_tendency: str = ""
    paragraph_density: str = ""
    dialogue_ratio: float = Field(default=0.35, ge=0.0, le=1.0)
    description_ratio: float = Field(default=0.35, ge=0.0, le=1.0)
    pacing: str = ""
    emotional_intensity: int = Field(default=5, ge=0, le=10)
    humor_level: int = Field(default=0, ge=0, le=10)
    imagery_preference: str = ""
    vocabulary_preference: str = ""
    rhythm_instructions: str = ""
    chapter_opening_preference: str = ""
    chapter_ending_preference: str = ""
    must_do_rules: list[str] = Field(default_factory=list)
    forbidden_rules: list[str] = Field(default_factory=list)
    avoided_phrases: list[str] = Field(default_factory=list)
    optional_user_sample: str = ""
    derived_style_anchors: list[str] = Field(default_factory=list)
    deterministic_rules: list[str] = Field(default_factory=list)
    writer_prompt_prefix: str = ""
    prompt_hash: str = ""
    read_only: bool = False
    source: Literal["preset", "user", "legacy"] = "user"
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator(
        "must_do_rules",
        "forbidden_rules",
        "avoided_phrases",
        "derived_style_anchors",
        "deterministic_rules",
        mode="before",
    )
    @classmethod
    def _normalise_lists(cls, value: Any) -> list[str]:
        return _normalise_string_list(value)

    def prompt_contract(self) -> dict[str, Any]:
        """Return only expression controls safe to place in Writer context."""

        return {
            "authority_boundary": (
                "Style controls expression only; NarrativeContract, StoryBible, "
                "CanonicalState, length limits, and story-thread state take precedence."
            ),
            "base_preset_key": self.base_preset_key,
            "description": self.description,
            "narrative_voice": self.narrative_voice,
            "viewpoint": self.viewpoint,
            "tense": self.tense,
            "sentence_length_tendency": self.sentence_length_tendency,
            "paragraph_density": self.paragraph_density,
            "dialogue_ratio": self.dialogue_ratio,
            "description_ratio": self.description_ratio,
            "pacing": self.pacing,
            "emotional_intensity": self.emotional_intensity,
            "humor_level": self.humor_level,
            "imagery_preference": self.imagery_preference,
            "vocabulary_preference": self.vocabulary_preference,
            "rhythm_instructions": self.rhythm_instructions,
            "chapter_opening_preference": self.chapter_opening_preference,
            "chapter_ending_preference": self.chapter_ending_preference,
            "must_do_rules": self.must_do_rules,
            "forbidden_rules": self.forbidden_rules,
            "avoided_phrases": self.avoided_phrases,
            "derived_style_anchors": self.derived_style_anchors,
            "deterministic_rules": self.deterministic_rules,
            "writer_prompt_prefix": self.writer_prompt_prefix,
        }

    def prompt_text(self) -> str:
        return json.dumps(
            self.prompt_contract(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def computed_prompt_hash(self) -> str:
        return hashlib.sha256(self.prompt_text().encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def _set_or_verify_prompt_hash(self) -> "StyleProfile":
        expected = self.computed_prompt_hash()
        if self.prompt_hash and self.prompt_hash != expected:
            raise ValueError("prompt_hash does not match the style prompt contract")
        object.__setattr__(self, "prompt_hash", expected)
        return self


class StyleProfileCreate(ProductionModel):
    name: str = Field(min_length=1)
    base_preset_key: str = ""
    description: str = ""
    narrative_voice: str = ""
    viewpoint: str = ""
    tense: str = ""
    sentence_length_tendency: str = ""
    paragraph_density: str = ""
    dialogue_ratio: float = Field(default=0.35, ge=0.0, le=1.0)
    description_ratio: float = Field(default=0.35, ge=0.0, le=1.0)
    pacing: str = ""
    emotional_intensity: int = Field(default=5, ge=0, le=10)
    humor_level: int = Field(default=0, ge=0, le=10)
    imagery_preference: str = ""
    vocabulary_preference: str = ""
    rhythm_instructions: str = ""
    chapter_opening_preference: str = ""
    chapter_ending_preference: str = ""
    must_do_rules: list[str] = Field(default_factory=list)
    forbidden_rules: list[str] = Field(default_factory=list)
    avoided_phrases: list[str] = Field(default_factory=list)
    optional_user_sample: str = ""
    derived_style_anchors: list[str] = Field(default_factory=list)
    deterministic_rules: list[str] = Field(default_factory=list)
    writer_prompt_prefix: str = ""


class StyleProfileUpdate(ProductionModel):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1)
    base_preset_key: str | None = None
    description: str | None = None
    narrative_voice: str | None = None
    viewpoint: str | None = None
    tense: str | None = None
    sentence_length_tendency: str | None = None
    paragraph_density: str | None = None
    dialogue_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    description_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    pacing: str | None = None
    emotional_intensity: int | None = Field(default=None, ge=0, le=10)
    humor_level: int | None = Field(default=None, ge=0, le=10)
    imagery_preference: str | None = None
    vocabulary_preference: str | None = None
    rhythm_instructions: str | None = None
    chapter_opening_preference: str | None = None
    chapter_ending_preference: str | None = None
    must_do_rules: list[str] | None = None
    forbidden_rules: list[str] | None = None
    avoided_phrases: list[str] | None = None
    optional_user_sample: str | None = None
    derived_style_anchors: list[str] | None = None
    deterministic_rules: list[str] | None = None
    writer_prompt_prefix: str | None = None


class ProductionContextSnapshot(ProductionModel):
    """Complete authority/style freeze taken before a section attempt."""

    schema_version: int = Field(default=1, ge=1)
    job_id: str = Field(min_length=1)
    job_revision: int = Field(ge=1)
    production_spec: NovelProductionSpec
    outline_revision: int = Field(ge=1)
    # Compatibility-only read path for attempts written before schema v2.
    # New attempts freeze the revision and chapter slice instead of copying
    # the entire book outline into every section journal.
    book_outline: BookOutline | None = None
    chapter_outline: ChapterOutline
    style_profile: StyleProfile
    story_bible_revision: int = Field(ge=1)
    canonical_state_revision: int = Field(ge=1)
    story_thread_revision: int = Field(ge=1)
    memory_revision: int = Field(ge=1)
    chapter_attempt: int = Field(ge=1)
    section_ordinal: int = Field(ge=1)
    section_target_chars: int = Field(ge=200)
    section_min_chars: int = Field(ge=1)
    section_max_chars: int = Field(ge=1)
    created_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_section_range(self) -> "ProductionContextSnapshot":
        if not (
            self.section_min_chars
            <= self.section_target_chars
            <= self.section_max_chars
        ):
            raise ValueError("section target must fit its frozen accepted range")
        return self


SectionAttemptStatus = Literal["in_progress", "committed", "rejected", "failed"]


class ProductionSectionAttempt(ProductionModel):
    """Production journal entry around one immutable author transaction."""

    schema_version: int = Field(default=1, ge=1)
    id: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)
    job_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    chapter_ordinal: int = Field(ge=1)
    section_id: str = Field(min_length=1)
    section_ordinal: int = Field(ge=1)
    attempt_number: int = Field(ge=1)
    transaction_id: str = Field(min_length=1)
    status: SectionAttemptStatus = "in_progress"
    snapshot: ProductionContextSnapshot
    committed_content: str = ""
    section_summary: str = ""
    char_count: int = Field(default=0, ge=0)
    canonical_revision_after: int = Field(default=0, ge=0)
    story_bible_revision: int = Field(default=0, ge=0)
    validation_passed: bool = False
    repair_performed: bool = False
    provider: str = ""
    provider_model: str = ""
    provider_source: str = ""
    provider_config_fingerprint: str = ""
    provider_config_fingerprints: list[str] = Field(default_factory=list)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    error_code: str = ""
    error_message: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _committed_attempt_has_only_committed_prose(
        self,
    ) -> "ProductionSectionAttempt":
        if self.status == "committed":
            if not self.committed_content:
                raise ValueError("committed attempt requires committed_content")
            if self.char_count != non_whitespace_char_count(self.committed_content):
                raise ValueError("committed attempt char_count does not match content")
            if not self.validation_passed:
                raise ValueError("committed attempt must have passed validation")
        elif self.committed_content:
            raise ValueError("non-committed attempt cannot retain candidate prose")
        return self


class CommittedProductionSection(ProductionModel):
    id: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    transaction_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    content: str = Field(min_length=1)
    summary: str = ""
    char_count: int = Field(ge=1)
    canonical_revision: int = Field(ge=1)
    story_bible_revision: int = Field(ge=1)
    validation_passed: Literal[True] = True
    repair_performed: bool = False
    provider: str = ""
    provider_model: str = ""
    provider_source: str = ""
    provider_config_fingerprint: str = ""
    provider_config_fingerprints: list[str] = Field(default_factory=list)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    committed_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_char_count(self) -> "CommittedProductionSection":
        if self.char_count != non_whitespace_char_count(self.content):
            raise ValueError("committed section char_count does not match content")
        return self


ChapterProductionStatus = Literal["generating", "failed", "committed"]


class ProductionChapterRecord(ProductionModel):
    """Derived committed-only chapter view and deterministic summary."""

    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    job_id: str = Field(min_length=1)
    chapter_id: str = Field(min_length=1)
    chapter_ordinal: int = Field(ge=1)
    volume_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: ChapterProductionStatus = "generating"
    expected_section_count: int = Field(ge=1)
    production_spec_revision: int = Field(ge=1)
    outline_revision: int = Field(ge=1)
    chapter_outline: ChapterOutline
    style_profile: StyleProfile
    sections: list[CommittedProductionSection] = Field(default_factory=list)
    char_count: int = Field(default=0, ge=0)
    summary: str = ""
    canonical_revision_start: int = Field(ge=1)
    canonical_revision_end: int = Field(default=0, ge=0)
    repair_total: int = Field(default=0, ge=0)
    validation_passed: bool = False
    failure_code: str = ""
    failure_message: str = ""
    created_at: str = Field(default_factory=utc_now)
    committed_at: str = ""
    updated_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_committed_sections(self) -> "ProductionChapterRecord":
        ordinals = [section.ordinal for section in self.sections]
        if ordinals != list(range(1, len(self.sections) + 1)):
            raise ValueError("committed chapter section ordinals must be contiguous")
        transaction_ids = [section.transaction_id for section in self.sections]
        if len(transaction_ids) != len(set(transaction_ids)):
            raise ValueError("committed chapter transaction IDs must be unique")
        expected_chars = sum(section.char_count for section in self.sections)
        if self.char_count != expected_chars:
            raise ValueError("chapter char_count does not match committed sections")
        if self.status == "committed":
            if len(self.sections) != self.expected_section_count:
                raise ValueError("committed chapter requires every expected section")
            if not self.validation_passed or not self.committed_at:
                raise ValueError("committed chapter requires validation and timestamp")
        return self

    def manuscript_text(self) -> str:
        if self.status != "committed":
            return ""
        return "\n\n".join(section.content for section in self.sections)


JobStatus = Literal[
    "draft",
    "queued",
    "running",
    "pausing",
    "paused",
    "failed",
    "cancelling",
    "cancelled",
    "completed",
]


class GenerationJob(ProductionModel):
    """Atomic durable coordinator state for a single novel."""

    schema_version: int = Field(default=1, ge=1)
    id: str = Field(min_length=1)
    novel_id: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)
    status: JobStatus = "draft"
    current_volume_id: str = ""
    current_volume_ordinal: int = Field(default=0, ge=0)
    current_chapter_id: str = ""
    current_chapter_ordinal: int = Field(default=0, ge=0)
    current_section_id: str = ""
    current_section_ordinal: int = Field(default=0, ge=0)
    completed_chapter_ids: list[str] = Field(default_factory=list)
    failed_chapter_id: str = ""
    requested_spec_revision: int = Field(ge=1)
    requested_outline_revision: int = Field(ge=1)
    requested_style_profile_id: str = Field(min_length=1)
    requested_style_revision: int = Field(ge=1)
    requested_style_prompt_hash: str = Field(min_length=64, max_length=64)
    requested_story_bible_revision: int = Field(default=1, ge=1)
    requested_canonical_revision: int = Field(default=1, ge=1)
    requested_spec_snapshot: NovelProductionSpec | None = None
    requested_outline_snapshot: BookOutline | None = None
    requested_style_snapshot: StyleProfile | None = None
    created_at: str = Field(default_factory=utc_now)
    started_at: str = ""
    paused_at: str = ""
    resumed_at: str = ""
    failed_at: str = ""
    completed_at: str = ""
    cancelled_at: str = ""
    updated_at: str = Field(default_factory=utc_now)
    lease_owner: str = ""
    lease_expiry: str = ""
    heartbeat: str = ""
    prompt_tokens_total: int = Field(default=0, ge=0)
    completion_tokens_total: int = Field(default=0, ge=0)
    latency_total_ms: int = Field(default=0, ge=0)
    repair_total: int = Field(default=0, ge=0)
    failure_code: str = ""
    failure_message: str = ""
    retry_count: int = Field(default=0, ge=0)
    cancellation_requested: bool = False
    last_committed_canonical_revision: int = Field(default=0, ge=0)
    active_transaction_id: str = ""
    chapter_attempts: dict[str, int] = Field(default_factory=dict)

    @field_validator("completed_chapter_ids")
    @classmethod
    def _unique_completed_chapters(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @field_validator("requested_style_prompt_hash")
    @classmethod
    def _valid_sha256(cls, value: str) -> str:
        if any(char not in "0123456789abcdef" for char in value.lower()):
            raise ValueError("requested_style_prompt_hash must be hexadecimal")
        return value.lower()

    @field_validator("chapter_attempts")
    @classmethod
    def _positive_attempts(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not chapter_id.strip() or attempt < 1 for chapter_id, attempt in value.items()):
            raise ValueError("chapter_attempts requires non-empty IDs and positive attempts")
        return value


class GenerationJobUpdate(ProductionModel):
    expected_revision: int = Field(ge=1)
    status: JobStatus | None = None
    current_volume_id: str | None = None
    current_volume_ordinal: int | None = Field(default=None, ge=0)
    current_chapter_id: str | None = None
    current_chapter_ordinal: int | None = Field(default=None, ge=0)
    current_section_id: str | None = None
    current_section_ordinal: int | None = Field(default=None, ge=0)
    completed_chapter_ids: list[str] | None = None
    failed_chapter_id: str | None = None
    lease_owner: str | None = None
    lease_expiry: str | None = None
    heartbeat: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    cancellation_requested: bool | None = None
    active_transaction_id: str | None = None


class ProductionStartOutcome(ProductionModel):
    job: GenerationJob
    existing: bool = False


class ProductionStartRequest(ProductionModel):
    expected_spec_revision: int = Field(ge=1)
    expected_outline_revision: int = Field(ge=1)


class GenerationJobControlRequest(ProductionModel):
    job_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
