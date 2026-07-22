"""Server-owned targeted prose repair plans and regression protection."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field

from story.event_execution import EventExecutionPlan
from story.narrative_contract import (
    NarrativeContract,
    NarrativeModel,
    NarrativeValidationReport,
    NarrativeViolation,
    narrative_char_count,
)


class RepairEventInstruction(NarrativeModel):
    event_id: str
    status: str
    actor: str = ""
    action: str
    target: str = ""
    completion_requirement: str
    minimum_completion_evidence: str = ""


class RepairEndStateInstruction(NarrativeModel):
    state_id: str
    path: str
    expected: Any
    current_evidence: str = ""


class RepairPreserveSpan(NarrativeModel):
    text: str = ""
    reason: str
    event_id: str = ""
    state_id: str = ""


class LengthAdjustment(NarrativeModel):
    current_chars: int = Field(ge=0)
    min_chars: int = Field(ge=1)
    max_chars: int = Field(ge=1)
    action: Literal["none", "add", "remove"] = "none"
    target_chars: int = Field(default=0, ge=0)


class RepairPlan(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    transaction_id: str
    original_contract_hash: str
    missing_events: list[RepairEventInstruction] = Field(default_factory=list)
    incomplete_events: list[RepairEventInstruction] = Field(default_factory=list)
    wrong_actor_events: list[RepairEventInstruction] = Field(default_factory=list)
    wrong_target_events: list[RepairEventInstruction] = Field(default_factory=list)
    wrong_end_states: list[RepairEndStateInstruction] = Field(default_factory=list)
    unsupported_additions: list[dict[str, str]] = Field(default_factory=list)
    length_adjustment: LengthAdjustment
    must_preserve_spans: list[RepairPreserveSpan] = Field(default_factory=list)
    must_preserve_facts: list[dict[str, Any]] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    style_constraints: dict[str, Any] = Field(default_factory=dict)
    repair_instruction: str

    @property
    def repair_context(self) -> dict[str, Any]:
        """Compatibility view for recorded writers while the plan stays authoritative."""
        return {
            "missing_required_events": [
                item.model_dump(mode="json")
                for item in [*self.missing_events, *self.incomplete_events]
            ],
            "wrong_end_states": [
                item.model_dump(mode="json") for item in self.wrong_end_states
            ],
        }


def _event_instruction(plan_event: Any, status: str) -> RepairEventInstruction:
    return RepairEventInstruction(
        event_id=plan_event.id,
        status=status,
        actor=plan_event.actor,
        action=plan_event.action,
        target=plan_event.target,
        completion_requirement=(
            "正文中必须由指定 actor 对指定 target 实际完成动作；"
            "准备、计划、未遂、假设、否定和仅提及均不算完成。"
        ),
        minimum_completion_evidence=plan_event.minimum_completion_evidence,
    )


class RepairPlanBuilder:
    """Translate deterministic reports into a minimal prose-only repair plan."""

    def build(
        self,
        *,
        transaction_id: str,
        contract: NarrativeContract,
        event_plan: EventExecutionPlan,
        narrative_report: NarrativeValidationReport,
        state_report: Any,
        narrative_text: str,
    ) -> RepairPlan:
        events = {item.id: item for item in event_plan.ordered_events}
        missing: list[RepairEventInstruction] = []
        incomplete: list[RepairEventInstruction] = []
        wrong_actor: list[RepairEventInstruction] = []
        wrong_target: list[RepairEventInstruction] = []
        preserve: list[RepairPreserveSpan] = []
        for result in narrative_report.event_results:
            planned = events[result.event_id]
            instruction = _event_instruction(planned, result.status)
            if result.status == "completed":
                preserve.append(
                    RepairPreserveSpan(
                        text=result.evidence if result.evidence in narrative_text else "",
                        reason=f"{result.event_id} 已完成",
                        event_id=result.event_id,
                    )
                )
            elif result.status == "missing":
                missing.append(instruction)
            elif result.status == "wrong_actor":
                wrong_actor.append(instruction)
            elif result.status == "wrong_target":
                wrong_target.append(instruction)
            else:
                incomplete.append(instruction)

        wrong_ends: list[RepairEndStateInstruction] = []
        for result in narrative_report.end_state_results:
            if result.reached:
                preserve.append(
                    RepairPreserveSpan(
                        text=result.evidence if result.evidence in narrative_text else "",
                        reason=f"{result.id} 已达到",
                        state_id=result.id,
                    )
                )
            else:
                wrong_ends.append(
                    RepairEndStateInstruction(
                        state_id=result.id,
                        path=result.path,
                        expected=result.expected,
                        current_evidence=result.evidence,
                    )
                )

        unsupported_codes = {
            "NARRATIVE_CHARACTER_ADDED",
            "NARRATIVE_RELATION_ADDED",
            "NARRATIVE_ORGANIZATION_ADDED",
        }
        unsupported = [
            {
                "code": item.code,
                "evidence": item.evidence,
                "message": item.message,
            }
            for item in narrative_report.violations
            if item.code.startswith("UNSUPPORTED_") or item.code in unsupported_codes
        ]
        chars = narrative_char_count(narrative_text)
        minimum = contract.length_constraint.min_chars
        maximum = contract.length_constraint.max_chars
        if chars < minimum:
            adjustment = LengthAdjustment(
                current_chars=chars,
                min_chars=minimum,
                max_chars=maximum,
                action="add",
                target_chars=minimum - chars,
            )
        elif chars > maximum:
            adjustment = LengthAdjustment(
                current_chars=chars,
                min_chars=minimum,
                max_chars=maximum,
                action="remove",
                target_chars=chars - maximum,
            )
        else:
            adjustment = LengthAdjustment(
                current_chars=chars,
                min_chars=minimum,
                max_chars=maximum,
                action="none",
            )

        proposal_codes = [
            item.code for item in getattr(state_report, "violations", [])
        ]
        return RepairPlan(
            transaction_id=transaction_id,
            original_contract_hash=contract.contract_hash,
            missing_events=missing,
            incomplete_events=incomplete,
            wrong_actor_events=wrong_actor,
            wrong_target_events=wrong_target,
            wrong_end_states=wrong_ends,
            unsupported_additions=unsupported,
            length_adjustment=adjustment,
            must_preserve_spans=preserve,
            must_preserve_facts=event_plan.preserve_facts,
            forbidden_changes=[
                "不得修改或返回 StateDelta",
                "不得修改或返回 StoryThread",
                "不得修改或返回 memory_records、title、section_summary 或 consistency_notes",
                "不得新增人物、关系、日期、数字、伤势、背景或支线",
                "不得删除已完成事件或已达到终态",
                *(["原结构化提案存在问题，将由服务端剔除: " + ", ".join(proposal_codes)] if proposal_codes else []),
            ],
            style_constraints=event_plan.style_constraints,
            repair_instruction=(
                "只修改正文：按事件顺序补齐缺失、未完成、动作人错误或对象错误的动作，"
                "在最后一段落实所有错误终态，删除明确的未授权新增，同时保持已完成事件；"
                "每个待修事件必须写出 minimum_completion_evidence 所要求的明确完成句，"
                "不得仅用气氛、暗示、动作开端或同义的计划句代替；"
                "返回完整修复后正文，不输出解释或任何结构化状态提案。"
            ),
        )


def repair_plan_prompt_payload(plan: RepairPlan, original_narrative: str) -> dict[str, Any]:
    return {
        "original_narrative": original_narrative,
        "missing_events": [item.model_dump(mode="json") for item in plan.missing_events],
        "incomplete_events": [item.model_dump(mode="json") for item in plan.incomplete_events],
        "wrong_actor_events": [item.model_dump(mode="json") for item in plan.wrong_actor_events],
        "wrong_target_events": [item.model_dump(mode="json") for item in plan.wrong_target_events],
        "wrong_end_states": [item.model_dump(mode="json") for item in plan.wrong_end_states],
        "unsupported_additions": plan.unsupported_additions,
        "length_adjustment": plan.length_adjustment.model_dump(mode="json"),
        "must_preserve_spans": [
            {"text": item.text, "reason": item.reason}
            for item in plan.must_preserve_spans
        ],
        "must_preserve_facts": plan.must_preserve_facts,
        "forbidden_changes": plan.forbidden_changes,
        "minimum_style_constraints": plan.style_constraints,
        "instruction": plan.repair_instruction,
        "output_contract": {"narrative_text": "修复后的完整正文"},
    }


class RepairRegressionValidator:
    def validate(
        self,
        *,
        plan: RepairPlan,
        final_report: NarrativeValidationReport,
        repaired_text: str,
    ) -> list[NarrativeViolation]:
        events = {item.event_id: item for item in final_report.event_results}
        end_states = {item.id: item for item in final_report.end_state_results}
        violations: list[NarrativeViolation] = []
        for preserved in plan.must_preserve_spans:
            valid = True
            if preserved.event_id:
                valid = events.get(preserved.event_id) is not None and (
                    events[preserved.event_id].status == "completed"
                )
            elif preserved.state_id:
                valid = end_states.get(preserved.state_id) is not None and end_states[
                    preserved.state_id
                ].reached
            elif preserved.text:
                valid = preserved.text in repaired_text
            if not valid:
                violations.append(
                    NarrativeViolation(
                        code="REPAIR_REGRESSION",
                        message=f"Repair 破坏了已通过内容: {preserved.reason}",
                        severity="high",
                        evidence=preserved.text[:180],
                        repair_hint="事务必须拒绝，不允许第二次 Repair",
                    )
                )
        return violations


_REMOVABLE_UNSUPPORTED_CODES = {
    "NARRATIVE_CHARACTER_ADDED",
    "NARRATIVE_RELATION_ADDED",
    "NARRATIVE_ORGANIZATION_ADDED",
}


def _remove_evidence_clause(text: str, evidence: str) -> str:
    """Remove the smallest punctuation-bounded clause containing evidence."""
    position = text.find(evidence)
    if position < 0:
        return text
    left = max(text.rfind(mark, 0, position) for mark in "，。！？；\n")
    evidence_end = position + len(evidence)
    right_candidates = [
        found
        for mark in "，。！？；\n"
        if (found := text.find(mark, evidence_end)) >= 0
    ]
    right = min(right_candidates, default=len(text))
    clause_start = left + 1
    if right >= len(text):
        cleaned = text[:clause_start]
    elif text[right] in "，；\n":
        cleaned = text[:clause_start] + text[right + 1 :]
    else:
        # Preserve the sentence terminator when the unsupported clause is the
        # final clause of a sentence.
        cleaned = text[:clause_start] + text[right:]
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"([。！？])[,，；]+", r"\1", cleaned)
    cleaned = re.sub(r"^[，；\s]+", "", cleaned)
    return cleaned.strip()


class DeterministicRepairEnforcer:
    """Delete only validator-proven unsupported clauses after the one Repair call.

    This is deliberately narrower than prose rewriting: required-event, end-state,
    length, fact and style violations are never modified here.  The caller must
    revalidate the entire contract and RepairRegression after every enforcement.
    """

    def enforce(
        self,
        *,
        report: NarrativeValidationReport,
        narrative_text: str,
    ) -> tuple[str, list[dict[str, str]]]:
        cleaned = narrative_text
        removals: list[dict[str, str]] = []
        for violation in report.violations:
            if not (
                violation.code.startswith("UNSUPPORTED_")
                or violation.code in _REMOVABLE_UNSUPPORTED_CODES
            ):
                continue
            evidence = violation.evidence.strip()
            if not evidence:
                continue
            updated = _remove_evidence_clause(cleaned, evidence)
            if updated == cleaned:
                continue
            cleaned = updated
            removals.append({"code": violation.code, "evidence": evidence})
        return cleaned, removals


__all__ = [
    "DeterministicRepairEnforcer",
    "LengthAdjustment",
    "RepairEndStateInstruction",
    "RepairEventInstruction",
    "RepairPlan",
    "RepairPlanBuilder",
    "RepairPreserveSpan",
    "RepairRegressionValidator",
    "repair_plan_prompt_payload",
]
