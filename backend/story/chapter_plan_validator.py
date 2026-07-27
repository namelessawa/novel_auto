"""Deterministic validation for ChapterPlan and Writer plan evidence."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from story.chapter_plan import ChapterEvidence, ChapterPlan
from story.event_execution import EventExecutionPlan
from story.narrative_contract import NarrativeModel
from story.section_budget import SectionBudgetPlan


class ChapterPlanViolation(NarrativeModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ChapterPlanValidationReport(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    accepted: bool = False
    violations: list[ChapterPlanViolation] = Field(default_factory=list)
    required_event_count: int = Field(default=0, ge=0)
    covered_event_count: int = Field(default=0, ge=0)
    required_end_state_count: int = Field(default=0, ge=0)
    covered_end_state_count: int = Field(default=0, ge=0)


class WriterPlanFollowReport(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    accepted: bool = False
    violations: list[ChapterPlanViolation] = Field(default_factory=list)
    required_event_count: int = Field(default=0, ge=0)
    evidenced_event_count: int = Field(default=0, ge=0)
    segment_evidence_count: int = Field(default=0, ge=0)


def _violation(code: str, message: str, **details: Any) -> ChapterPlanViolation:
    return ChapterPlanViolation(code=code, message=message, details=details)


class ChapterPlanValidator:
    """Ensure the LLM planner only allocates frozen server-owned authorities."""

    _PURPOSE_BY_ORDER = {
        1: "opening",
        2: "development",
        3: "conflict",
        4: "resolution",
    }

    def validate(
        self,
        *,
        plan: ChapterPlan,
        event_plan: EventExecutionPlan,
        budget_plan: SectionBudgetPlan,
    ) -> ChapterPlanValidationReport:
        violations: list[ChapterPlanViolation] = []
        if plan.section_id != budget_plan.section_id:
            violations.append(
                _violation(
                    "PLAN_SECTION_MISMATCH",
                    "ChapterPlan section_id does not match the frozen section.",
                    expected=budget_plan.section_id,
                    actual=plan.section_id,
                )
            )
        if plan.target_chars != budget_plan.target_chars:
            violations.append(
                _violation(
                    "PLAN_TARGET_MISMATCH",
                    "ChapterPlan target_chars must equal SectionBudgetPlan.",
                    expected=budget_plan.target_chars,
                    actual=plan.target_chars,
                )
            )

        orders = [item.order for item in plan.segments]
        purposes = {item.order: item.purpose for item in plan.segments}
        if sorted(orders) != [1, 2, 3, 4] or any(
            purposes.get(order) != purpose
            for order, purpose in self._PURPOSE_BY_ORDER.items()
        ):
            violations.append(
                _violation(
                    "PLAN_STRUCTURE_INVALID",
                    "Plan must contain opening/development/conflict/resolution in order.",
                    orders=orders,
                    purposes=purposes,
                )
            )
        segment_chars = sum(item.target_chars for item in plan.segments)
        if segment_chars != plan.target_chars:
            violations.append(
                _violation(
                    "PLAN_BUDGET_MISMATCH",
                    "Segment target_chars must sum exactly to plan target_chars.",
                    segment_chars=segment_chars,
                    target_chars=plan.target_chars,
                )
            )

        required_events = {
            item.id
            for item in event_plan.ordered_events
            if item.required and not item.allow_omission
        }
        declared_events = set(plan.required_events)
        assigned_events = {
            event_id for segment in plan.segments for event_id in segment.events
        }
        missing_events = sorted(required_events - assigned_events)
        if missing_events:
            violations.append(
                _violation(
                    "PLAN_EVENT_MISSING",
                    "Every required event must be bound to at least one segment.",
                    event_ids=missing_events,
                )
            )
        undeclared_required = sorted(required_events - declared_events)
        if undeclared_required:
            violations.append(
                _violation(
                    "PLAN_EVENT_MISSING",
                    "ChapterPlan.required_events omitted frozen required events.",
                    event_ids=undeclared_required,
                )
            )
        added_events = sorted((assigned_events | declared_events) - required_events)
        if added_events:
            violations.append(
                _violation(
                    "PLAN_EVENT_ADDED",
                    "Planner may not add events or arbitrary entity references.",
                    references=added_events,
                )
            )
            prefix_codes = {
                "character:": "PLAN_EXTRA_CHARACTER",
                "location:": "PLAN_EXTRA_LOCATION",
                "item:": "PLAN_EXTRA_ITEM",
                "organization:": "PLAN_EXTRA_ORGANIZATION",
            }
            for prefix, code in prefix_codes.items():
                references = [
                    item for item in added_events if item.startswith(prefix)
                ]
                if references:
                    violations.append(
                        _violation(
                            code,
                            "Planner referenced an entity outside frozen events.",
                            references=references,
                        )
                    )
        duplicates = sorted(
            {
                event_id
                for event_id in required_events
                if sum(event_id in segment.events for segment in plan.segments) > 1
            }
        )
        if duplicates:
            violations.append(
                _violation(
                    "PLAN_EVENT_DUPLICATED",
                    "A required event may be allocated to only one segment.",
                    event_ids=duplicates,
                )
            )
        expected_order = [
            item.id
            for item in event_plan.ordered_events
            if item.id in required_events
        ]
        assigned_order = [
            event_id
            for segment in sorted(plan.segments, key=lambda item: item.order)
            for event_id in segment.events
            if event_id in required_events
        ]
        if (
            not missing_events
            and not duplicates
            and assigned_order != expected_order
        ):
            violations.append(
                _violation(
                    "PLAN_EVENT_ORDER_INVALID",
                    "Planner must preserve EventExecutionPlan order.",
                    expected=expected_order,
                    actual=assigned_order,
                )
            )

        required_end_states = {item.id for item in event_plan.required_end_states}
        declared_end_states = set(plan.required_end_states)
        missing_end_states = sorted(required_end_states - declared_end_states)
        has_resolution = any(
            item.order == 4 and item.purpose == "resolution"
            for item in plan.segments
        )
        if missing_end_states or (required_end_states and not has_resolution):
            violations.append(
                _violation(
                    "PLAN_END_STATE_MISSING",
                    "Required end states must be declared with a resolution segment.",
                    state_ids=missing_end_states,
                    resolution_present=has_resolution,
                )
            )
        added_end_states = sorted(declared_end_states - required_end_states)
        if added_end_states:
            violations.append(
                _violation(
                    "PLAN_END_STATE_ADDED",
                    "Planner may not add end states.",
                    references=added_end_states,
                )
            )

        expected_stops = set(budget_plan.stop_conditions)
        actual_stops = set(plan.stop_condition)
        if not expected_stops.issubset(actual_stops):
            violations.append(
                _violation(
                    "PLAN_STOP_CONDITION_MISSING",
                    "Plan must preserve all server stop conditions.",
                    stop_conditions=sorted(expected_stops - actual_stops),
                )
            )
        added_stops = sorted(actual_stops - expected_stops)
        if added_stops:
            violations.append(
                _violation(
                    "PLAN_UNAUTHORIZED_REFERENCE",
                    "Planner stop conditions may not introduce facts or entities.",
                    references=added_stops,
                )
            )

        return ChapterPlanValidationReport(
            accepted=not violations,
            violations=violations,
            required_event_count=len(required_events),
            covered_event_count=len(required_events & assigned_events),
            required_end_state_count=len(required_end_states),
            covered_end_state_count=len(required_end_states & declared_end_states),
        )


class WriterPlanEvidenceValidator:
    """Validate only the Writer's debug trace; prose validators stay authoritative."""

    def validate(
        self,
        *,
        plan: ChapterPlan,
        evidence: list[ChapterEvidence],
    ) -> WriterPlanFollowReport:
        violations: list[ChapterPlanViolation] = []
        evidence_by_segment: dict[int, list[str]] = {}
        for item in evidence:
            if item.segment in evidence_by_segment:
                violations.append(
                    _violation(
                        "PLAN_EVIDENCE_SEGMENT_DUPLICATED",
                        "Only one evidence record is allowed per segment.",
                        segment=item.segment,
                    )
                )
            evidence_by_segment.setdefault(item.segment, []).extend(
                item.events_completed
            )
        missing_segments = sorted(
            {item.order for item in plan.segments} - set(evidence_by_segment)
        )
        if missing_segments:
            violations.append(
                _violation(
                    "PLAN_EVIDENCE_SEGMENT_MISSING",
                    "Writer did not report evidence for every planned segment.",
                    segments=missing_segments,
                )
            )

        expected_by_event = {
            event_id: segment.order
            for segment in plan.segments
            for event_id in segment.events
        }
        actual_by_event = {
            event_id: segment
            for segment, event_ids in evidence_by_segment.items()
            for event_id in event_ids
        }
        missing_events = sorted(set(expected_by_event) - set(actual_by_event))
        if missing_events:
            violations.append(
                _violation(
                    "PLAN_EVIDENCE_EVENT_MISSING",
                    "Writer evidence omitted planned events.",
                    event_ids=missing_events,
                )
            )
        unknown_events = sorted(set(actual_by_event) - set(expected_by_event))
        if unknown_events:
            violations.append(
                _violation(
                    "PLAN_EVIDENCE_EVENT_ADDED",
                    "Writer evidence contains events outside the plan.",
                    event_ids=unknown_events,
                )
            )
        misplaced = sorted(
            event_id
            for event_id in set(expected_by_event) & set(actual_by_event)
            if expected_by_event[event_id] != actual_by_event[event_id]
        )
        if misplaced:
            violations.append(
                _violation(
                    "PLAN_EVIDENCE_EVENT_MISPLACED",
                    "Writer reported planned events in the wrong segment.",
                    event_ids=misplaced,
                )
            )
        return WriterPlanFollowReport(
            accepted=not violations,
            violations=violations,
            required_event_count=len(expected_by_event),
            evidenced_event_count=len(set(expected_by_event) & set(actual_by_event)),
            segment_evidence_count=len(evidence_by_segment),
        )


__all__ = [
    "ChapterPlanValidationReport",
    "ChapterPlanValidator",
    "ChapterPlanViolation",
    "WriterPlanEvidenceValidator",
    "WriterPlanFollowReport",
]
