"""Bounded, section-local planning contract for the author Writer.

The plan is not canon, memory, or a second generation agent.  It may only
allocate events and end states that already exist in the frozen section
authorities.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from story.event_execution import EventExecutionPlan
from story.narrative_contract import NarrativeModel
from story.section_budget import SectionBudgetPlan


ChapterPlanPurpose = Literal[
    "opening",
    "development",
    "conflict",
    "resolution",
]


class ChapterPlanSegment(NarrativeModel):
    order: int = Field(ge=1, le=4)
    purpose: ChapterPlanPurpose
    target_chars: int = Field(ge=1)
    events: list[str] = Field(default_factory=list)

    @field_validator("events", mode="before")
    @classmethod
    def _normalise_events(cls, value) -> list:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]


class ChapterPlan(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    section_id: str = Field(min_length=1)
    target_chars: int = Field(ge=1)
    segments: list[ChapterPlanSegment] = Field(min_length=4, max_length=4)
    required_events: list[str] = Field(default_factory=list)
    required_end_states: list[str] = Field(default_factory=list)
    stop_condition: list[str] = Field(default_factory=list)

    @field_validator(
        "required_events",
        "required_end_states",
        "stop_condition",
        mode="before",
    )
    @classmethod
    def _normalise_lists(cls, value) -> list:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]


class ChapterEvidence(NarrativeModel):
    """Writer-reported plan trace; useful for diagnostics, never authoritative."""

    segment: int = Field(ge=1, le=4)
    events_completed: list[str] = Field(default_factory=list)

    @field_validator("events_completed", mode="before")
    @classmethod
    def _normalise_events(cls, value) -> list:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]


class ChapterPlanBuilder:
    """Create a safe fallback plan for injected/legacy Writers in offline tests."""

    _PURPOSES: tuple[ChapterPlanPurpose, ...] = (
        "opening",
        "development",
        "conflict",
        "resolution",
    )

    def build(
        self,
        *,
        event_plan: EventExecutionPlan,
        budget_plan: SectionBudgetPlan,
    ) -> ChapterPlan:
        required_events = [
            item.id
            for item in event_plan.ordered_events
            if item.required and not item.allow_omission
        ]
        event_buckets: list[list[str]] = [[] for _ in self._PURPOSES]
        if len(required_events) == 1:
            event_buckets[2].append(required_events[0])
        else:
            # Preserve event order while keeping resolution free to land state.
            writable = (0, 1, 2)
            for index, event_id in enumerate(required_events):
                bucket = writable[min(index * len(writable) // max(1, len(required_events)), 2)]
                event_buckets[bucket].append(event_id)
        return ChapterPlan(
            section_id=budget_plan.section_id,
            target_chars=budget_plan.target_chars,
            segments=[
                ChapterPlanSegment(
                    order=index,
                    purpose=purpose,
                    target_chars=budget.budget,
                    events=event_buckets[index - 1],
                )
                for index, (purpose, budget) in enumerate(
                    zip(self._PURPOSES, budget_plan.segments, strict=True),
                    start=1,
                )
            ],
            required_events=required_events,
            required_end_states=[
                item.id for item in event_plan.required_end_states
            ],
            stop_condition=list(budget_plan.stop_conditions),
        )


def chapter_plan_prompt_payload(plan: ChapterPlan) -> dict:
    return plan.model_dump(mode="json")


__all__ = [
    "ChapterEvidence",
    "ChapterPlan",
    "ChapterPlanBuilder",
    "ChapterPlanPurpose",
    "ChapterPlanSegment",
    "chapter_plan_prompt_payload",
]
