"""Pydantic contracts for the default author generation path."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from story.event_execution import EventExecutionPlan
from story.narrative_contract import (
    NarrativeContract,
    NarrativeContractInput,
    NarrativeValidationReport,
)
from story.ending_validator import EndingCompletionReport
from story.repair_patch import RepairPatchSet, RepairPatchValidationReport
from story.repair_plan import RepairPlan
from story.section_budget import SectionBudgetPlan
from story.section_length_validator import SectionBalanceReport, SectionLengthReport
from story.writer_preflight import WriterPreflightReport
from story.writing_plan import SectionWritingPlan


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _listify(value: Any) -> list[Any]:
    """Normalize common OpenAI-compatible singleton-list drift."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


class StoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MigrationMetadata(StoryModel):
    source: Literal["new", "legacy_inferred", "user_confirmed"] = "new"
    migration_version: int = Field(default=1, ge=1)
    inferred_fields: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    needs_confirmation: bool = False


class StoryBible(StoryModel):
    """Highest authority for theme, setting rules, and creative promises."""

    # source_seed is an audit field: whitespace and line breaks are user data,
    # not formatting noise.  List fields are normalised explicitly below.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    title: str = ""
    source_seed: str = ""
    theme_key: str = ""
    positioning: str = ""
    reference_preferences: list[str] = Field(default_factory=list)
    premise: str = ""
    theme: str = ""
    central_question: str = ""
    genre: str = ""
    setting_summary: str = ""
    immutable_world_rules: list[str] = Field(default_factory=list)
    forbidden_deviations: list[str] = Field(default_factory=list)
    protagonist_contracts: list[str] = Field(default_factory=list)
    main_conflicts: list[str] = Field(default_factory=list)
    ending_direction: str = ""
    style_contract: dict[str, Any] = Field(default_factory=dict)
    field_provenance: dict[
        str,
        Literal["user_input", "preset_derived", "llm_inferred", "legacy_inferred"],
    ] = Field(default_factory=dict)
    migration: MigrationMetadata = Field(default_factory=MigrationMetadata)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @field_validator(
        "immutable_world_rules",
        "forbidden_deviations",
        "protagonist_contracts",
        "main_conflicts",
        "reference_preferences",
    )
    @classmethod
    def _normalise_unique_lines(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    def publish_errors(self) -> list[str]:
        errors: list[str] = []
        for field, label in (
            ("premise", "故事前提"),
            ("theme", "主题"),
            ("setting_summary", "背景摘要"),
        ):
            if not getattr(self, field).strip():
                errors.append(f"{label}不能为空")
        return errors


class StoryBibleUpdate(StoryModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    expected_revision: int = Field(ge=1)
    title: str = ""
    source_seed: str = ""
    theme_key: str = ""
    positioning: str = ""
    reference_preferences: list[str] = Field(default_factory=list)
    premise: str
    theme: str
    central_question: str = ""
    genre: str = ""
    setting_summary: str
    immutable_world_rules: list[str] = Field(default_factory=list)
    forbidden_deviations: list[str] = Field(default_factory=list)
    protagonist_contracts: list[str] = Field(default_factory=list)
    main_conflicts: list[str] = Field(default_factory=list)
    ending_direction: str = ""
    style_contract: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "immutable_world_rules",
        "forbidden_deviations",
        "protagonist_contracts",
        "main_conflicts",
        "reference_preferences",
    )
    @classmethod
    def _normalise_unique_lines(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @model_validator(mode="after")
    def _required_contract(self) -> "StoryBibleUpdate":
        missing = [
            name
            for name in ("premise", "theme", "setting_summary")
            if not getattr(self, name).strip()
        ]
        if missing:
            raise ValueError("required StoryBible fields are empty: " + ", ".join(missing))
        return self


ThreadType = Literal["mystery", "conflict", "promise", "threat", "goal"]
ThreadStatus = Literal[
    "open",
    "advancing",
    "resolved",
    "abandoned",
    "stale",
    "needs_attention",
]


class StoryThread(StoryModel):
    id: str = Field(min_length=1)
    type: ThreadType = "mystery"
    description: str = Field(min_length=1)
    promised_question: str = ""
    involved_characters: list[str] = Field(default_factory=list)
    origin_refs: list[str] = Field(default_factory=list)
    status: ThreadStatus = "open"
    urgency: int = Field(default=5, ge=0, le=10)
    resolution_requirements: list[str] = Field(default_factory=list)
    resolution_evidence: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    opened_at_revision: int = Field(default=0, ge=0)
    updated_at_revision: int = Field(default=0, ge=0)
    source: Literal["author", "simulation", "legacy_inferred"] = "author"

    @field_validator(
        "involved_characters",
        "origin_refs",
        "resolution_requirements",
        "resolution_evidence",
        "evidence",
        mode="before",
    )
    @classmethod
    def _normalise_lists(cls, value: Any) -> list[Any]:
        return _listify(value)


class StoryThreadRepository(StoryModel):
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    threads: dict[str, StoryThread] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=utc_now)


MemoryType = Literal[
    "event",
    "decision",
    "relationship_change",
    "revelation",
    "promise",
    "consequence",
]


class MemoryRecord(StoryModel):
    id: str = Field(min_length=1)
    type: MemoryType = "event"
    section_id: str = ""
    entities: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    evidence: str = ""
    importance: int = Field(default=5, ge=0, le=10)
    canon_status: Literal["confirmed", "uncertain", "superseded"] = "confirmed"
    source_refs: list[str] = Field(default_factory=list)
    created_at_revision: int = Field(default=0, ge=0)

    @field_validator("entities", "source_refs", mode="before")
    @classmethod
    def _normalise_lists(cls, value: Any) -> list[Any]:
        return _listify(value)

    @model_validator(mode="before")
    @classmethod
    def _normalise_description_alias(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "description" not in value:
            return value
        payload = dict(value)
        if not payload.get("summary"):
            payload["summary"] = payload["description"]
        payload.pop("description", None)
        return payload


class MemoryRepositoryState(StoryModel):
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    records: dict[str, MemoryRecord] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=utc_now)


class CanonicalState(StoryModel):
    """Only authority for current mutable facts."""

    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    world_time: int = Field(default=0, ge=0)
    world: dict[str, Any] = Field(default_factory=dict)
    characters: dict[str, dict[str, Any]] = Field(default_factory=dict)
    items: dict[str, dict[str, Any]] = Field(default_factory=dict)
    relationships: dict[str, Any] = Field(default_factory=dict)
    character_knowledge: dict[str, list[str]] = Field(default_factory=dict)
    reader_knowledge: dict[str, Any] = Field(default_factory=dict)
    active_threads: dict[str, Any] = Field(default_factory=dict)
    plot_position: dict[str, Any] = Field(default_factory=dict)
    last_scene_state: dict[str, Any] = Field(default_factory=dict)
    canonical_facts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    migration: MigrationMetadata = Field(default_factory=MigrationMetadata)
    updated_at: str = Field(default_factory=utc_now)


class SectionGoal(StoryModel):
    section_id: str = ""
    objective: str = Field(min_length=1)
    viewpoint_character_id: str = ""
    location_id: str = ""
    involved_characters: list[str] = Field(default_factory=list)
    target_threads: list[str] = Field(default_factory=list)
    desired_length: int = Field(default=1800, ge=200, le=10000)
    narrative_constraints: NarrativeContractInput = Field(
        default_factory=NarrativeContractInput
    )


StateOperationKind = Literal["set", "add", "append", "remove", "transfer"]


class StateDeltaOperation(StoryModel):
    op: StateOperationKind
    path: str = Field(min_length=2, pattern=r"^/")
    value: Any = None
    evidence: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ThreadChange(StoryModel):
    action: Literal["opened", "advanced", "resolved"]
    thread: StoryThread


class EventEvidenceHint(StoryModel):
    event_id: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class EndStateEvidenceHint(StoryModel):
    state_id: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class WriterCandidate(StoryModel):
    narrative_text: str = Field(min_length=1)
    section_summary: str = Field(min_length=1)
    event_evidence: list[EventEvidenceHint] = Field(default_factory=list)
    end_state_evidence: list[EndStateEvidenceHint] = Field(default_factory=list)
    state_delta: list[StateDeltaOperation] = Field(default_factory=list)
    threads_opened: list[StoryThread] = Field(default_factory=list)
    threads_advanced: list[StoryThread] = Field(default_factory=list)
    threads_resolved: list[StoryThread] = Field(default_factory=list)
    memory_records: list[MemoryRecord] = Field(default_factory=list)
    consistency_notes: list[str] = Field(default_factory=list)
    title: str = ""

    @field_validator(
        "state_delta",
        "event_evidence",
        "end_state_evidence",
        "threads_opened",
        "threads_advanced",
        "threads_resolved",
        "memory_records",
        "consistency_notes",
        mode="before",
    )
    @classmethod
    def _normalise_lists(cls, value: Any) -> list[Any]:
        return _listify(value)


ViolationSeverity = Literal["low", "medium", "high"]


class ValidationViolation(StoryModel):
    code: str
    message: str
    severity: ViolationSeverity
    path: str = ""
    evidence: str = ""
    repair_hint: str = ""


class ValidationReport(StoryModel):
    accepted: bool = False
    severity: ViolationSeverity = "low"
    violations: list[ValidationViolation] = Field(default_factory=list)
    repairable: bool = True
    validated_delta: list[StateDeltaOperation] = Field(default_factory=list)
    thread_changes: list[ThreadChange] = Field(default_factory=list)
    proposal_drops: list[ValidationViolation] = Field(default_factory=list)
    dropped_delta_count: int = Field(default=0, ge=0)
    dropped_thread_change_count: int = Field(default=0, ge=0)
    repair_context: dict[str, Any] = Field(default_factory=dict)


class ContextSlotManifest(StoryModel):
    name: str
    char_count: int = Field(ge=0)
    token_estimate: int = Field(ge=0)
    budget_chars: int = Field(ge=0)
    truncated: bool = False
    reference_ids: list[str] = Field(default_factory=list)
    selected_count: int = Field(default=0, ge=0)
    omitted_count: int = Field(default=0, ge=0)
    duplicate_ratio: float = Field(default=0.0, ge=0.0, le=1.0)


class ContextManifest(StoryModel):
    schema_version: int = Field(default=1, ge=1)
    novel_id: str
    section_id: str
    story_bible_revision: int = Field(ge=1)
    canonical_state_revision: int = Field(ge=1)
    total_chars: int = Field(ge=0)
    total_token_estimate: int = Field(ge=0)
    max_context_chars: int = Field(default=0, ge=0)
    max_context_token_estimate: int = Field(default=0, ge=0)
    budget_utilization: float = Field(default=0.0, ge=0.0)
    rejected_reason: str = ""
    slots: list[ContextSlotManifest] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


TransactionPhase = Literal[
    "prepared",
    "generated",
    "validated",
    "committing",
    "committed",
    "stale_context",
    "rejected",
    "failed",
]


class GenerationTransaction(StoryModel):
    schema_version: int = Field(default=1, ge=1)
    id: str
    user_id: str
    novel_id: str
    section_id: str
    phase: TransactionPhase = "prepared"
    story_bible_revision: int = Field(ge=1)
    canonical_state_revision: int = Field(ge=1)
    target_canonical_revision: int = Field(ge=1)
    journal_canonical_revision: int = Field(default=1, ge=1)
    writer_calls: int = Field(default=0, ge=0, le=3)
    writer_retry_count: int = Field(default=0, ge=0, le=1)
    writer_retry_performed: bool = False
    writer_first_pass_pass: bool = False
    repair_performed: bool = False
    committed: bool = False
    candidate: WriterCandidate | None = None
    candidate_history: list[WriterCandidate] = Field(default_factory=list)
    narrative_contract: NarrativeContract | None = None
    event_execution_plan: EventExecutionPlan | None = None
    section_writing_plan: SectionWritingPlan | None = None
    section_budget_plan: SectionBudgetPlan | None = None
    initial_preflight_report: WriterPreflightReport | None = None
    final_preflight_report: WriterPreflightReport | None = None
    initial_length_report: SectionLengthReport | None = None
    final_length_report: SectionLengthReport | None = None
    initial_ending_report: EndingCompletionReport | None = None
    final_ending_report: EndingCompletionReport | None = None
    initial_balance_report: SectionBalanceReport | None = None
    final_balance_report: SectionBalanceReport | None = None
    repair_plan: RepairPlan | None = None
    repair_patches: RepairPatchSet | None = None
    repair_patch_report: RepairPatchValidationReport | None = None
    repair_ignored_fields: list[str] = Field(default_factory=list)
    repair_audit_codes: list[str] = Field(default_factory=list)
    repair_enforced_removals: list[dict[str, str]] = Field(default_factory=list)
    narrative_validation_report: NarrativeValidationReport | None = None
    narrative_validation_history: list[NarrativeValidationReport] = Field(
        default_factory=list
    )
    validation_report: ValidationReport | None = None
    validation_history: list[ValidationReport] = Field(default_factory=list)
    style_validation_report: dict[str, Any] = Field(default_factory=dict)
    context_manifest: ContextManifest | None = None
    base_canonical_state: dict[str, Any] = Field(default_factory=dict)
    base_story_threads: dict[str, Any] = Field(default_factory=dict)
    base_memory_repository: dict[str, Any] = Field(default_factory=dict)
    target_canonical_state: dict[str, Any] = Field(default_factory=dict)
    target_story_threads: dict[str, Any] = Field(default_factory=dict)
    target_memory_repository: dict[str, Any] = Field(default_factory=dict)
    section_record: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    recovery_count: int = Field(default=0, ge=0)
    error_code: str = ""
    error: str = ""
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)


class GenerationModeConfig(StoryModel):
    schema_version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    mode: Literal["author", "simulation"] = "author"
    updated_at: str = Field(default_factory=utc_now)


class GenerationModeUpdate(StoryModel):
    expected_revision: int = Field(ge=1)
    mode: Literal["author", "simulation"]


class MigrationReport(StoryModel):
    schema_version: int = 1
    migration_version: int = 1
    status: Literal["created", "migrated", "already_current", "partial"]
    source_files: list[str] = Field(default_factory=list)
    inferred_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    completed_at: str = Field(default_factory=utc_now)
