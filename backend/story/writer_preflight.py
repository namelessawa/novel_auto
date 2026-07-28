"""Lightweight deterministic checks between Writer generation and validation."""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field

from story.event_execution import EventExecutionPlan
from story.narrative_contract import (
    NarrativeContract,
    NarrativeModel,
    NarrativeValidationReport,
    narrative_char_count,
)
from story.narrative_validator import NarrativeContractValidator
from story.section_budget import SectionBudgetPlan


class WriterPreflightIssue(NarrativeModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class WriterPreflightSegment(NarrativeModel):
    name: str
    expected_ratio: float = Field(ge=0.0, le=1.0)
    actual_ratio: float = Field(ge=0.0, le=1.0)
    char_count: int = Field(ge=0)
    sentence_count: int = Field(ge=0)
    present: bool


class WriterPreflightReport(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    accepted: bool = False
    retry_required: bool = True
    chars: int = Field(ge=0)
    target_chars: int = Field(ge=1)
    min_chars: int = Field(ge=1)
    max_chars: int = Field(ge=1)
    length_pass: bool = False
    structure_pass: bool = False
    event_pass: bool = False
    end_state_pass: bool = False
    event_coverage: float = Field(ge=0.0, le=1.0)
    event_coverage_threshold: float = Field(ge=0.0, le=1.0)
    completed_events: int = Field(ge=0)
    required_events: int = Field(ge=0)
    reached_end_states: int = Field(ge=0)
    required_end_states: int = Field(ge=0)
    segments: list[WriterPreflightSegment] = Field(default_factory=list)
    issues: list[WriterPreflightIssue] = Field(default_factory=list)

    def retry_reasons(self) -> list[str]:
        return [f"{item.code}: {item.message}" for item in self.issues]


_SENTENCE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


def _substantive_sentences(text: str) -> list[str]:
    return [
        item.group(0).strip()
        for item in _SENTENCE.finditer(text or "")
        if narrative_char_count(item.group(0)) > 0
    ]


def _structure_segments(
    text: str,
    plan: SectionBudgetPlan,
) -> list[WriterPreflightSegment]:
    """Assign prose sentences to server-owned proportional content bands.

    This deliberately ignores headings. A band exists only when substantive
    prose falls inside its cumulative share of the section.
    """
    sentences = _substantive_sentences(text)
    lengths = [narrative_char_count(item) for item in sentences]
    total = sum(lengths)
    budget_total = sum(item.budget for item in plan.segments)
    boundaries: list[float] = []
    used = 0
    for item in plan.segments:
        used += item.budget
        boundaries.append(used / max(1, budget_total))

    segment_chars = [0 for _ in plan.segments]
    segment_sentences = [0 for _ in plan.segments]
    cursor = 0
    for chars in lengths:
        midpoint = (cursor + chars / 2) / max(1, total)
        index = next(
            (
                candidate
                for candidate, boundary in enumerate(boundaries)
                if midpoint <= boundary
            ),
            len(plan.segments) - 1,
        )
        segment_chars[index] += chars
        segment_sentences[index] += 1
        cursor += chars

    reports: list[WriterPreflightSegment] = []
    for index, item in enumerate(plan.segments):
        expected_ratio = item.budget / max(1, budget_total)
        actual_ratio = segment_chars[index] / max(1, total)
        # The threshold is intentionally tolerant of sentence-boundary drift.
        # Its purpose is to catch missing content bands, not enforce prose shape.
        minimum_ratio = max(0.03, expected_ratio * 0.25)
        reports.append(
            WriterPreflightSegment(
                name=item.name,
                expected_ratio=round(expected_ratio, 4),
                actual_ratio=round(actual_ratio, 4),
                char_count=segment_chars[index],
                sentence_count=segment_sentences[index],
                present=(
                    segment_sentences[index] > 0
                    and actual_ratio >= minimum_ratio
                ),
            )
        )
    return reports


class WriterPreflightValidator:
    """Emit structured, provider-free issues for the one RepairPlan."""

    def __init__(
        self,
        *,
        event_coverage_threshold: float = 1.0,
        narrative_validator: NarrativeContractValidator | None = None,
    ) -> None:
        self.event_coverage_threshold = max(
            0.0, min(float(event_coverage_threshold), 1.0)
        )
        self.narrative_validator = (
            narrative_validator or NarrativeContractValidator()
        )

    def validate(
        self,
        *,
        candidate: Any,
        contract: NarrativeContract,
        event_plan: EventExecutionPlan,
        budget_plan: SectionBudgetPlan,
    ) -> WriterPreflightReport:
        text = str(getattr(candidate, "narrative_text", "") or "")
        chars = narrative_char_count(text)
        narrative_report: NarrativeValidationReport = (
            self.narrative_validator.validate(
                contract,
                text,
                event_execution_plan=event_plan,
                event_evidence=list(
                    getattr(candidate, "event_evidence", []) or []
                ),
                end_state_evidence=list(
                    getattr(candidate, "end_state_evidence", []) or []
                ),
            )
        )
        required_events = len(narrative_report.event_results)
        completed_events = sum(
            item.status == "completed"
            for item in narrative_report.event_results
        )
        event_coverage = (
            completed_events / required_events if required_events else 1.0
        )
        required_end_states = len(narrative_report.end_state_results)
        reached_end_states = sum(
            item.reached for item in narrative_report.end_state_results
        )
        end_state_coverage = (
            reached_end_states / required_end_states
            if required_end_states
            else 1.0
        )
        segments = _structure_segments(text, budget_plan)
        length_pass = budget_plan.min_chars <= chars <= budget_plan.max_chars
        structure_pass = all(item.present for item in segments)
        event_pass = event_coverage >= self.event_coverage_threshold
        end_state_pass = end_state_coverage >= 1.0

        issues: list[WriterPreflightIssue] = []
        if chars < budget_plan.min_chars:
            issues.append(
                WriterPreflightIssue(
                    code="PREFLIGHT_TOO_SHORT",
                    message=(
                        f"初稿 {chars} 字，低于下限 {budget_plan.min_chars} 字"
                    ),
                    details={"chars": chars, "min_chars": budget_plan.min_chars},
                )
            )
        elif chars > budget_plan.max_chars:
            issues.append(
                WriterPreflightIssue(
                    code="PREFLIGHT_TOO_LONG",
                    message=(
                        f"初稿 {chars} 字，超过上限 {budget_plan.max_chars} 字"
                    ),
                    details={"chars": chars, "max_chars": budget_plan.max_chars},
                )
            )
        missing_segments = [item.name for item in segments if not item.present]
        if missing_segments:
            issues.append(
                WriterPreflightIssue(
                    code="PREFLIGHT_STRUCTURE_INCOMPLETE",
                    message="正文内容比例缺少必要结构段: "
                    + ", ".join(missing_segments),
                    details={"missing_segments": missing_segments},
                )
            )
        if not event_pass:
            missing_events = [
                item.event_id
                for item in narrative_report.event_results
                if item.status != "completed"
            ]
            issues.append(
                WriterPreflightIssue(
                    code="PREFLIGHT_EVENT_COVERAGE_LOW",
                    message=(
                        f"必要事件覆盖 {event_coverage:.2%}，低于阈值 "
                        f"{self.event_coverage_threshold:.2%}"
                    ),
                    details={"missing_events": missing_events},
                )
            )
        if not end_state_pass:
            missing_states = [
                item.id
                for item in narrative_report.end_state_results
                if not item.reached
            ]
            issues.append(
                WriterPreflightIssue(
                    code="PREFLIGHT_END_STATE_UNREACHABLE",
                    message="正文未明确达到全部最终状态",
                    details={"missing_end_states": missing_states},
                )
            )

        accepted = (
            length_pass
            and structure_pass
            and event_pass
            and end_state_pass
        )
        return WriterPreflightReport(
            accepted=accepted,
            retry_required=not accepted,
            chars=chars,
            target_chars=budget_plan.target_chars,
            min_chars=budget_plan.min_chars,
            max_chars=budget_plan.max_chars,
            length_pass=length_pass,
            structure_pass=structure_pass,
            event_pass=event_pass,
            end_state_pass=end_state_pass,
            event_coverage=round(event_coverage, 4),
            event_coverage_threshold=self.event_coverage_threshold,
            completed_events=completed_events,
            required_events=required_events,
            reached_end_states=reached_end_states,
            required_end_states=required_end_states,
            segments=segments,
            issues=issues,
        )


__all__ = [
    "WriterPreflightIssue",
    "WriterPreflightReport",
    "WriterPreflightSegment",
    "WriterPreflightValidator",
]
