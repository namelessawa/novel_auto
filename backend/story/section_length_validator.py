"""Deterministic initial/final section-length evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story.ending_validator import EndingCompletionReport
from story.narrative_contract import NarrativeModel, NarrativeViolation, narrative_char_count
from story.narrative_contract import NarrativeValidationReport
from story.section_budget import SectionBudgetPlan
from story.writing_plan import SectionWritingPlan


LengthValidationPhase = Literal["initial", "repaired", "final"]


class SectionLengthReport(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    phase: LengthValidationPhase
    chars: int = Field(ge=0)
    target: int = Field(ge=1)
    min_chars: int = Field(ge=1)
    max_chars: int = Field(ge=1)
    ratio: float = Field(ge=0.0)
    accepted: bool
    violation_code: str = ""


class SectionLengthValidator:
    def validate(
        self,
        narrative_text: str,
        plan: SectionWritingPlan | SectionBudgetPlan,
        *,
        phase: LengthValidationPhase,
    ) -> SectionLengthReport:
        chars = narrative_char_count(narrative_text)
        code = ""
        if chars < plan.min_chars:
            code = "NARRATIVE_TOO_SHORT"
        elif chars > plan.max_chars:
            code = "NARRATIVE_TOO_LONG"
        return SectionLengthReport(
            phase=phase,
            chars=chars,
            target=plan.target_chars,
            min_chars=plan.min_chars,
            max_chars=plan.max_chars,
            ratio=round(chars / plan.target_chars, 4),
            accepted=not code,
            violation_code=code,
        )

    @staticmethod
    def violation(report: SectionLengthReport) -> NarrativeViolation | None:
        if report.accepted:
            return None
        if report.violation_code == "NARRATIVE_TOO_SHORT":
            message = (
                f"正文仅 {report.chars} 字，低于服务端 WritingPlan 最低 "
                f"{report.min_chars} 字"
            )
            hint = "只扩写现有动作、环境、互动或情绪，不得新增事件、人物或事实"
        else:
            message = (
                f"正文共 {report.chars} 字，超过服务端 WritingPlan 最高 "
                f"{report.max_chars} 字"
            )
            hint = "只删除非必要描写，不得删除必需事件或最终状态"
        return NarrativeViolation(
            code=report.violation_code,
            message=message,
            severity="high",
            path="/length_constraint",
            evidence=str(report.chars),
            repair_hint=hint,
        )


class SectionBalanceReport(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    phase: LengthValidationPhase
    event_pass: bool
    end_state_pass: bool
    length_pass: bool
    ending_pass: bool
    accepted: bool


class SectionBalanceValidator:
    """Explicit Event AND EndState AND Length AND Ending gate."""

    @staticmethod
    def validate(
        *,
        narrative_report: NarrativeValidationReport,
        length_report: SectionLengthReport,
        ending_report: EndingCompletionReport,
        phase: LengthValidationPhase,
    ) -> SectionBalanceReport:
        event_pass = all(
            item.status == "completed"
            for item in narrative_report.event_results
        )
        end_state_pass = all(
            item.reached for item in narrative_report.end_state_results
        )
        length_pass = length_report.accepted
        ending_pass = ending_report.accepted
        return SectionBalanceReport(
            phase=phase,
            event_pass=event_pass,
            end_state_pass=end_state_pass,
            length_pass=length_pass,
            ending_pass=ending_pass,
            accepted=(
                event_pass
                and end_state_pass
                and length_pass
                and ending_pass
            ),
        )


__all__ = [
    "LengthValidationPhase",
    "SectionBalanceReport",
    "SectionBalanceValidator",
    "SectionLengthReport",
    "SectionLengthValidator",
]
