"""Server-owned targeted prose repair plans and regression protection."""

from __future__ import annotations

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
    actor_aliases: list[str] = Field(default_factory=list)
    action: str
    target: str = ""
    target_aliases: list[str] = Field(default_factory=list)
    current_evidence: str = ""
    completion_requirement: str
    minimum_completion_evidence: str = ""


class RepairEndStateInstruction(NarrativeModel):
    state_id: str
    path: str
    expected: Any
    current_evidence: str = ""
    minimum_completion_evidence: str = ""


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


def _event_instruction(
    plan_event: Any,
    status: str,
    current_evidence: str = "",
) -> RepairEventInstruction:
    return RepairEventInstruction(
        event_id=plan_event.id,
        status=status,
        actor=plan_event.actor,
        actor_aliases=plan_event.actor_aliases,
        action=plan_event.action,
        target=plan_event.target,
        target_aliases=plan_event.target_aliases,
        current_evidence=current_evidence,
        completion_requirement=(
            "正文中必须由指定 actor 对指定 target 实际完成动作；"
            "准备、计划、未遂、假设、否定和仅提及均不算完成。"
        ),
        minimum_completion_evidence=plan_event.minimum_completion_evidence,
    )


def _display_name(contract: NarrativeContract, identifier: str) -> str:
    for group in (
        contract.allowed_entities.characters,
        contract.allowed_entities.locations,
        contract.allowed_entities.items,
        contract.allowed_entities.organizations,
    ):
        for item in group:
            if identifier in item.all_names:
                return next(
                    (name for name in item.all_names if name != identifier),
                    item.name or identifier,
                )
    return identifier


def _end_state_completion_evidence(
    contract: NarrativeContract,
    path: str,
    expected: Any,
) -> str:
    parts = [part for part in path.split("/") if part]
    expected_name = _display_name(contract, str(expected))
    if len(parts) >= 2 and parts[-1] in {"holder", "owner", "owners"}:
        item_name = _display_name(contract, parts[-2])
        return (
            f"{expected_name}将{item_name}收好并继续保管，"
            f"{item_name}最终由{expected_name}持有。"
        )
    subject = _display_name(contract, parts[-2] if len(parts) >= 2 else path)
    return f"{subject}的最终状态已经明确变为“{expected}”。"


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
            instruction = _event_instruction(
                planned,
                result.status,
                result.evidence,
            )
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
                        minimum_completion_evidence=_end_state_completion_evidence(
                            contract,
                            result.path,
                            result.expected,
                        ),
                    )
                )

        preserved_texts = {item.text for item in preserve if item.text}
        for fact in event_plan.preserve_facts:
            statement = str(fact.get("statement") or "")
            if (
                statement
                and statement in narrative_text
                and statement not in preserved_texts
            ):
                preserve.append(
                    RepairPreserveSpan(
                        text=statement,
                        reason=f"{fact.get('id') or 'required_fact'} 已通过",
                    )
                )
                preserved_texts.add(statement)

        unsupported_codes = {
            "NARRATIVE_CHARACTER_ADDED",
            "NARRATIVE_RELATION_ADDED",
            "NARRATIVE_ORGANIZATION_ADDED",
            "FORBIDDEN_OUTCOME_MENTIONED",
            "TIME_CONSTRAINT_MUTATED",
            "CAUSAL_LINK_WEAKENED",
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
        has_higher_priority_issue = bool(
            missing
            or incomplete
            or wrong_actor
            or wrong_target
            or wrong_ends
            or unsupported
        )
        if has_higher_priority_issue:
            # A single Repair call must first complete events/end states or
            # delete unsupported facts.  The model may not spend that call on
            # free-form length padding.
            adjustment = LengthAdjustment(
                current_chars=chars,
                min_chars=minimum,
                max_chars=maximum,
                action="none",
            )
        elif chars < minimum:
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
                "只输出局部 patches：优先完成事件，其次落实最终状态，再删除未授权新增，"
                "仅在没有前三类问题时处理长度；每个 patch 只能解决明确列出的 target，"
                "必须使用正文中唯一的逐字 anchor，不得重写整篇正文。"
            ),
        )


def _window(
    narrative: str,
    evidence: str,
    *,
    radius: int = 260,
) -> dict[str, Any] | None:
    if not evidence:
        return None
    position = narrative.find(evidence)
    if position < 0:
        return None
    start = max(0, position - radius)
    end = min(len(narrative), position + len(evidence) + radius)
    return {
        "start": start,
        "end": end,
        "text": narrative[start:end],
    }


def _unique_tail_anchor(narrative: str) -> str:
    stripped = narrative.rstrip()
    for size in (240, 180, 120, 90, 60, 48, 36, 28, 20, 14):
        anchor = stripped[-size:]
        if anchor and narrative.count(anchor) == 1:
            return anchor
    for size in (240, 180, 120, 90, 60, 48, 36, 28, 20, 14):
        anchor = stripped[:size]
        if anchor and narrative.count(anchor) == 1:
            return anchor
    for size in (240, 180, 120, 90, 60, 48, 36, 28, 20, 14):
        for end in range(len(stripped), size - 1, -max(1, size // 2)):
            anchor = stripped[end - size : end]
            if anchor and narrative.count(anchor) == 1:
                return anchor
    return stripped[-240:]


def _length_addition_text(narrative: str, target_chars: int) -> str:
    """Reuse existing prose for a conservative length-only patch template."""
    stripped = narrative.rstrip()
    if not stripped:
        return ""
    required = min(300, max(1, target_chars))
    source_chars = sum(not char.isspace() for char in stripped)
    if source_chars == 0:
        return ""
    source: list[str] = []
    source_count = 0
    for char in reversed(stripped):
        source.append(char)
        if not char.isspace():
            source_count += 1
        if source_count >= required:
            break
    suffix = "".join(reversed(source))
    suffix_chars = sum(not char.isspace() for char in suffix)
    repeated = suffix * max(1, (required + suffix_chars - 1) // suffix_chars)
    selected: list[str] = []
    count = 0
    for char in repeated:
        selected.append(char)
        if not char.isspace():
            count += 1
        if count >= required:
            break
    return "".join(selected)


def _length_removal_text(plan: RepairPlan, narrative: str) -> str:
    """Select a unique tail span outside already-approved evidence."""
    protected: list[tuple[int, int]] = []
    for item in plan.must_preserve_spans:
        if not item.text:
            continue
        start = narrative.find(item.text)
        if start >= 0:
            protected.append((start, start + len(item.text)))

    target = min(300, max(1, plan.length_adjustment.target_chars))
    run_end = len(narrative)
    while run_end > 0:
        overlapping = [
            (start, end)
            for start, end in protected
            if start < run_end and end > 0
        ]
        blocking = max(overlapping, key=lambda item: item[1], default=None)
        run_start = blocking[1] if blocking and blocking[1] < run_end else 0
        if blocking and blocking[1] >= run_end:
            run_end = blocking[0]
            continue

        count = 0
        start = run_end
        while start > run_start and count < target:
            start -= 1
            if not narrative[start].isspace():
                count += 1
        selected = narrative[start:run_end]
        if count >= target and narrative.count(selected) == 1:
            return selected
        run_end = run_start
    return ""


def _repair_windows(plan: RepairPlan, narrative: str) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    evidence_values = [
        item.current_evidence
        for item in [
            *plan.incomplete_events,
            *plan.wrong_actor_events,
            *plan.wrong_target_events,
        ]
    ]
    evidence_values.extend(item.current_evidence for item in plan.wrong_end_states)
    evidence_values.extend(
        str(item.get("evidence") or "") for item in plan.unsupported_additions
    )
    for evidence in evidence_values:
        selected = _window(narrative, evidence)
        if selected and selected not in windows:
            windows.append(selected)
    tail_start = max(0, len(narrative) - 700)
    tail = {"start": tail_start, "end": len(narrative), "text": narrative[tail_start:]}
    if tail not in windows:
        windows.append(tail)
    return windows


def _suggested_patch_templates(
    plan: RepairPlan,
    original_narrative: str,
) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    delete_templates: list[dict[str, Any]] = []
    delete_evidence_seen: set[str] = set()
    for item in plan.unsupported_additions:
        evidence = str(item.get("evidence") or "")
        if (
            evidence
            and evidence not in delete_evidence_seen
            and original_narrative.count(evidence) == 1
        ):
            delete_evidence_seen.add(evidence)
            delete_templates.append(
                {
                    "patch_type": "delete",
                    "anchor": {"before_text": evidence, "after_text": ""},
                    "patch_text": "",
                    "target_events": [],
                    "target_end_states": [],
                    "max_chars": 300,
                    "preserve": [],
                }
            )

    pending_events = [
        *plan.missing_events,
        *plan.incomplete_events,
        *plan.wrong_actor_events,
        *plan.wrong_target_events,
    ]
    event_text = "".join(
        item.minimum_completion_evidence for item in pending_events
    )
    combined_text = event_text
    for item in plan.wrong_end_states:
        if item.minimum_completion_evidence not in combined_text:
            combined_text += item.minimum_completion_evidence
    if combined_text:
        templates.append(
            {
                "patch_type": "insert",
                "anchor": {
                    "before_text": _unique_tail_anchor(original_narrative),
                    "after_text": "",
                },
                "patch_text": combined_text[:300],
                "target_events": [item.event_id for item in pending_events],
                "target_end_states": [
                    item.state_id for item in plan.wrong_end_states
                ],
                "max_chars": 300,
                "preserve": [
                    item.text for item in plan.must_preserve_spans if item.text
                ],
            }
        )
    elif plan.length_adjustment.action == "add":
        patch_text = _length_addition_text(
            original_narrative,
            plan.length_adjustment.target_chars,
        )
        if patch_text:
            templates.append(
                {
                    "patch_type": "insert",
                    "anchor": {
                        "before_text": _unique_tail_anchor(original_narrative),
                        "after_text": "",
                    },
                    "patch_text": patch_text,
                    "target_events": [],
                    "target_end_states": [],
                    "max_chars": 300,
                    "preserve": [
                        item.text for item in plan.must_preserve_spans if item.text
                    ],
                }
            )
    elif plan.length_adjustment.action == "remove":
        target_text = _length_removal_text(plan, original_narrative)
        if target_text:
            templates.append(
                {
                    "patch_type": "delete",
                    "anchor": {
                        "before_text": target_text,
                        "after_text": "",
                    },
                    "patch_text": "",
                    "target_events": [],
                    "target_end_states": [],
                    "max_chars": 300,
                    "preserve": [
                        item.text for item in plan.must_preserve_spans if item.text
                    ],
                }
            )
    # Apply inserts/replacements before deletes so a deletion cannot invalidate
    # a later anchor that was selected from the original prose.
    templates.extend(delete_templates)
    return templates


def repair_patch_prompt_payload(
    plan: RepairPlan,
    original_narrative: str,
) -> dict[str, Any]:
    suggested_templates = _suggested_patch_templates(
        plan,
        original_narrative,
    )
    return {
        "execution_mode": (
            "COPY_SUGGESTED_TEMPLATES_EXACTLY"
            if suggested_templates
            else "GENERATE_LOCAL_PATCHES"
        ),
        "required_patches": suggested_templates,
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
        "priority_order": [
            "event_completion",
            "required_end_state",
            "unsupported_addition_delete",
            "length_only_when_no_higher_priority_issue",
        ],
        "relevant_windows": _repair_windows(plan, original_narrative),
        "suggested_patch_templates": suggested_templates,
        "output_contract": {
            "patches": [
                {
                    "patch_type": "insert|replace|delete",
                    "anchor": {"before_text": "逐字锚点", "after_text": ""},
                    "patch_text": "不超过 300 字的局部修改",
                    "target_events": [],
                    "target_end_states": [],
                    "max_chars": 300,
                    "preserve": [],
                }
            ]
        },
        "final_instruction": (
            "required_patches 非空：只返回 {\"patches\": required_patches}，"
            "数组内每个字段和每个字符必须原样复制，不得同义改写。"
            if suggested_templates
            else "required_patches 为空：按 output_contract 生成最小局部 patches。"
        ),
    }


def repair_plan_prompt_payload(plan: RepairPlan, original_narrative: str) -> dict[str, Any]:
    """Backward-compatible name; the payload is patch-only."""
    return repair_patch_prompt_payload(plan, original_narrative)


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


__all__ = [
    "LengthAdjustment",
    "RepairEndStateInstruction",
    "RepairEventInstruction",
    "RepairPlan",
    "RepairPlanBuilder",
    "RepairPreserveSpan",
    "RepairRegressionValidator",
    "repair_patch_prompt_payload",
    "repair_plan_prompt_payload",
]
