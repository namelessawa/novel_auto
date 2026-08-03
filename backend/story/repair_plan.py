"""Server-owned targeted prose repair plans and regression protection."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import Field, model_validator

from story.ending_validator import EndingCompletionReport
from story.event_execution import EventExecutionPlan
from story.narrative_contract import (
    NarrativeContract,
    NarrativeModel,
    NarrativeValidationReport,
    NarrativeViolation,
    narrative_char_count,
)
from story.writing_plan import SectionWritingPlan


_PROVIDER_REPAIR_CELL_NAMES = ("beat_1", "beat_2", "beat_3")


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
    desired_final_chars: int = Field(default=0, ge=0)
    max_add_chars: int = Field(default=0, ge=0)


class PreflightRepairIssue(NarrativeModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


RepairPatchType = Literal["insert", "replace", "delete", "expand", "compact"]


class ServerRepairPatchTemplate(NarrativeModel):
    """Immutable server authority for one bounded repair operation.

    Provider output is never parsed into this model.  The provider may supply
    prose only for templates with ``provider_text_required``; every placement,
    scope, target, preservation, length, and authority field remains frozen.
    """

    schema_version: int = Field(default=1, ge=1)
    patch_id: str = Field(min_length=1, max_length=128)
    patch_type: RepairPatchType
    exact_anchor: str = Field(default="", max_length=240)
    insertion_offset: int | None = Field(default=None, ge=0)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    target_events: list[str] = Field(default_factory=list)
    target_end_states: list[str] = Field(default_factory=list)
    min_chars: int = Field(default=0, ge=0, le=450)
    target_chars: int = Field(default=0, ge=0, le=450)
    max_chars: int = Field(default=300, ge=1, le=450)
    preserve: list[str] = Field(default_factory=list)
    purpose: str = Field(default="", max_length=240)
    remove_reason: str = Field(default="", max_length=240)
    max_remove_chars: int = Field(default=0, ge=0, le=300)
    original_narrative_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    contract_hash: str = Field(min_length=1)
    provider_text_required: bool = False
    server_patch_text: str | None = Field(default=None, max_length=600)

    @model_validator(mode="after")
    def validate_frozen_placement_and_text(self) -> "ServerRepairPatchTemplate":
        if self.patch_type in {"insert", "expand"}:
            if self.insertion_offset is None:
                raise ValueError("insert/expand template requires insertion_offset")
            if self.start_offset is not None or self.end_offset is not None:
                raise ValueError("insert/expand template cannot carry an edit range")
        elif (
            self.start_offset is None
            or self.end_offset is None
            or self.end_offset < self.start_offset
        ):
            raise ValueError("replace/delete/compact template requires a valid range")
        if self.provider_text_required:
            if self.patch_type != "expand":
                raise ValueError("only expand may require provider prose")
            if self.server_patch_text is not None:
                raise ValueError("provider template cannot carry server patch prose")
            if (
                self.min_chars
                and not self.min_chars <= self.target_chars <= self.max_chars
            ) or self.target_chars > self.max_chars:
                raise ValueError(
                    "provider template requires min <= target <= max chars"
                )
        elif self.server_patch_text is None:
            raise ValueError("deterministic template requires server patch prose")
        elif self.min_chars:
            raise ValueError("deterministic template cannot require provider min chars")
        return self


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
    post_resolution_expansions: list[dict[str, Any]] = Field(default_factory=list)
    preflight_issues: list[PreflightRepairIssue] = Field(default_factory=list)
    length_adjustment: LengthAdjustment
    must_preserve_spans: list[RepairPreserveSpan] = Field(default_factory=list)
    must_preserve_facts: list[dict[str, Any]] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    style_constraints: dict[str, Any] = Field(default_factory=dict)
    repair_instruction: str
    patch_templates: list[ServerRepairPatchTemplate] = Field(
        default_factory=list,
        max_length=8,
    )

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
            "preflight_issues": [
                item.model_dump(mode="json") for item in self.preflight_issues
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
        section_writing_plan: SectionWritingPlan | None = None,
        section_target_chars: int | None = None,
        ending_report: EndingCompletionReport | None = None,
        preflight_report: Any = None,
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

        for operation in getattr(state_report, "validated_delta", []):
            evidence = str(getattr(operation, "evidence", "") or "")
            if evidence and evidence in narrative_text and evidence not in preserved_texts:
                preserve.append(
                    RepairPreserveSpan(
                        text=evidence,
                        reason="CanonicalState delta evidence 已通过",
                    )
                )
                preserved_texts.add(evidence)
        for change in getattr(state_report, "thread_changes", []):
            evidence = str(
                getattr(getattr(change, "thread", None), "resolution_evidence", "")
                or ""
            )
            if evidence and evidence in narrative_text and evidence not in preserved_texts:
                preserve.append(
                    RepairPreserveSpan(
                        text=evidence,
                        reason="StoryThread evidence 已通过",
                    )
                )
                preserved_texts.add(evidence)

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
        minimum = (
            section_writing_plan.min_chars
            if section_writing_plan is not None
            else contract.length_constraint.min_chars
        )
        maximum = (
            section_writing_plan.max_chars
            if section_writing_plan is not None
            else contract.length_constraint.max_chars
        )
        desired_lower = min(maximum, minimum + 80)
        desired_upper = max(minimum, maximum - 50)
        if desired_lower > desired_upper:
            desired_lower, desired_upper = minimum, maximum
        desired = (
            int(section_target_chars)
            if section_target_chars is not None
            else desired_lower
        )
        desired = max(desired_lower, min(desired, desired_upper))
        if chars < minimum:
            adjustment = LengthAdjustment(
                current_chars=chars,
                min_chars=minimum,
                max_chars=maximum,
                action="add",
                target_chars=max(0, desired - chars),
                desired_final_chars=desired,
                max_add_chars=max(0, maximum - chars),
            )
        elif chars > maximum:
            adjustment = LengthAdjustment(
                current_chars=chars,
                min_chars=minimum,
                max_chars=maximum,
                action="remove",
                target_chars=chars - maximum,
                desired_final_chars=desired,
            )
        else:
            adjustment = LengthAdjustment(
                current_chars=chars,
                min_chars=minimum,
                max_chars=maximum,
                action="none",
                desired_final_chars=desired,
            )

        proposal_codes = [
            item.code for item in getattr(state_report, "violations", [])
        ]
        plan = RepairPlan(
            transaction_id=transaction_id,
            original_contract_hash=contract.contract_hash,
            missing_events=missing,
            incomplete_events=incomplete,
            wrong_actor_events=wrong_actor,
            wrong_target_events=wrong_target,
            wrong_end_states=wrong_ends,
            unsupported_additions=unsupported,
            post_resolution_expansions=[
                item.model_dump(mode="json")
                for item in (ending_report.issues if ending_report else [])
            ],
            preflight_issues=[
                PreflightRepairIssue.model_validate(
                    item.model_dump(mode="json")
                )
                for item in (
                    getattr(preflight_report, "issues", []) or []
                )
            ],
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
                "然后才允许用 EXPAND 或 COMPACT 处理长度；每个 patch 只能解决明确列出的 target，"
                "只能为服务端 patch_id 生成获准的局部正文，不得返回或修改位置、长度、target、"
                "preserve、原文 hash 或契约 hash，不得重写整篇正文。"
            ),
        )
        return plan.model_copy(
            update={
                "patch_templates": build_server_patch_templates(
                    plan=plan,
                    original_narrative=narrative_text,
                    contract_hash=contract.contract_hash,
                )
            }
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
    # Apply inserts/replacements before deletes so a deletion cannot invalidate
    # a later anchor that was selected from the original prose.
    templates.extend(delete_templates)
    return templates


_COMPACT_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")


def _template_delta(template: dict[str, Any]) -> int:
    if template.get("patch_type") in {"delete", "compact"}:
        anchor = template.get("anchor") or {}
        target = (
            anchor.get("start")
            or anchor.get("before_text")
            or ""
        )
        return -narrative_char_count(str(target))
    return narrative_char_count(str(template.get("patch_text") or ""))


def compact_patch_templates(
    plan: RepairPlan,
    original_narrative: str,
    *,
    base_templates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Select exact removable prose while excluding every protected evidence span."""
    base = (
        list(base_templates)
        if base_templates is not None
        else _suggested_patch_templates(plan, original_narrative)
    )
    projected_chars = (
        plan.length_adjustment.current_chars
        + sum(_template_delta(item) for item in base)
    )
    remaining = max(0, projected_chars - plan.length_adjustment.max_chars)
    issue_evidence = {
        str(item.get("evidence") or "")
        for item in plan.post_resolution_expansions
        if item.get("evidence")
    }
    if not remaining and not issue_evidence:
        return []

    protected_texts = [
        item.text for item in plan.must_preserve_spans if item.text
    ]
    protected_texts.extend(
        str((item.get("anchor") or {}).get("before_text") or "")
        for item in base
        if item.get("patch_type") == "delete"
    )
    protected_ranges: list[tuple[int, int]] = []
    for protected in protected_texts:
        start = original_narrative.find(protected)
        if start >= 0:
            protected_ranges.append((start, start + len(protected)))
    preserve_refs = [
        item.event_id or item.state_id
        for item in plan.must_preserve_spans
        if item.event_id or item.state_id
    ]

    candidates: list[tuple[str, str]] = []
    for evidence in issue_evidence:
        candidates.append((evidence, "remove post-resolution expansion"))
    for match in reversed(list(_COMPACT_SENTENCE.finditer(original_narrative))):
        text = match.group(0).strip()
        candidates.append(
            (text, "remove redundant style detail to satisfy section maximum")
        )

    selected: list[dict[str, Any]] = []
    selected_texts: set[str] = set()
    selected_ranges: list[tuple[int, int]] = []
    pending_issue_evidence = set(issue_evidence)
    for text, reason in candidates:
        if not text or text in selected_texts:
            continue
        if original_narrative.count(text) != 1:
            continue
        start = original_narrative.find(text)
        end = start + len(text)
        if any(start < right and end > left for left, right in protected_ranges):
            continue
        if any(start < right and end > left for left, right in selected_ranges):
            continue
        chars = narrative_char_count(text)
        if chars <= 0 or chars > 200:
            continue
        is_issue = text in pending_issue_evidence
        if not is_issue and remaining <= 0:
            continue
        selected.append(
            {
                "patch_type": "compact",
                "anchor": {"start": text, "end": ""},
                "patch_text": "",
                "target_events": [],
                "target_end_states": [],
                "max_chars": 300,
                "preserve": preserve_refs,
                "target_chars": 0,
                "purpose": "",
                "remove_reason": reason,
                "max_remove_chars": chars,
            }
        )
        selected_texts.add(text)
        selected_ranges.append((start, end))
        pending_issue_evidence.discard(text)
        remaining = max(0, remaining - chars)
        if len(base) + len(selected) >= 8:
            break
        if remaining <= 0 and not pending_issue_evidence:
            break
    return selected


_NONEMPTY_PARAGRAPH = re.compile(r"[^\r\n]+")


def _paragraph_ranges(narrative: str) -> list[tuple[int, int]]:
    return [
        (match.start(), match.end())
        for match in _NONEMPTY_PARAGRAPH.finditer(narrative)
        if match.group(0).strip()
    ]


def _paragraph_start(
    paragraphs: list[tuple[int, int]],
    position: int,
) -> int | None:
    for start, end in paragraphs:
        if start <= position < end:
            return start
    return None


def _safe_expansion_offset(
    plan: RepairPlan,
    narrative: str,
    *,
    deletion_ranges: list[tuple[int, int]],
) -> int:
    """Choose a stable pre-terminal insertion boundary in authority order."""
    paragraphs = _paragraph_ranges(narrative)
    end_state_positions = [
        narrative.find(item.text)
        for item in plan.must_preserve_spans
        if item.state_id and item.text and narrative.find(item.text) >= 0
    ]
    if end_state_positions:
        earliest = min(end_state_positions)
        offset = _paragraph_start(paragraphs, earliest)
        offset = earliest if offset is None else offset
    else:
        event_evidence = [
            (narrative.rfind(item.text), item.text)
            for item in plan.must_preserve_spans
            if item.text and narrative.rfind(item.text) >= 0
        ]
        pending_event_instructions = [
            *plan.missing_events,
            *plan.incomplete_events,
            *plan.wrong_actor_events,
            *plan.wrong_target_events,
        ]
        event_evidence.extend(
            (narrative.rfind(item.current_evidence), item.current_evidence)
            for item in pending_event_instructions
            if (
                item.current_evidence
                and narrative.rfind(item.current_evidence) >= 0
            )
        )
        target_terms = {
            term
            for item in pending_event_instructions
            for term in [item.target, *item.target_aliases]
            if term
        }
        for sentence in _COMPACT_SENTENCE.finditer(narrative):
            text = sentence.group(0)
            if target_terms and any(term in text for term in target_terms):
                event_evidence.append((sentence.start(), text))
        if event_evidence:
            position, evidence = max(event_evidence, key=lambda item: item[0])
            evidence_end = position + len(evidence)
            closure = re.search(r"[。！？!?]", narrative[evidence_end:])
            offset = (
                evidence_end + closure.end()
                if closure is not None
                else evidence_end
            )
        elif paragraphs:
            offset = paragraphs[-1][0]
        else:
            offset = 0

    # An insertion at a boundary is safe.  If an authority bug ever selects an
    # interior position, fail closed by moving to the beginning of that range.
    for preserved in plan.must_preserve_spans:
        if not preserved.text:
            continue
        start = narrative.find(preserved.text)
        if start < 0:
            continue
        end = start + len(preserved.text)
        if start < offset < end:
            offset = start
    for start, end in deletion_ranges:
        if start < offset < end:
            offset = start
    return max(0, min(offset, len(narrative)))


def _server_patch_id(
    *,
    plan: RepairPlan,
    index: int,
    patch_type: RepairPatchType,
    placement: str,
    targets: list[str],
) -> str:
    authority = "|".join(
        [
            plan.transaction_id,
            str(index),
            patch_type,
            placement,
            *targets,
        ]
    )
    digest = hashlib.sha256(authority.encode("utf-8")).hexdigest()[:16]
    return f"repair-{index:02d}-{digest}"


def _template_delta_from_model(
    template: ServerRepairPatchTemplate,
    narrative: str,
) -> int:
    if template.patch_type in {"delete", "compact"}:
        assert template.start_offset is not None
        assert template.end_offset is not None
        return -narrative_char_count(
            narrative[template.start_offset : template.end_offset]
        )
    if template.patch_type == "replace":
        assert template.start_offset is not None
        assert template.end_offset is not None
        removed = narrative_char_count(
            narrative[template.start_offset : template.end_offset]
        )
        inserted = narrative_char_count(template.server_patch_text or "")
        return inserted - removed
    return narrative_char_count(template.server_patch_text or "")


def _distribute_integer(total: int, count: int) -> list[int]:
    """Distribute a frozen total deterministically without losing a character."""

    if count <= 0:
        return []
    quotient, remainder = divmod(max(0, total), count)
    return [
        quotient + int(index < remainder)
        for index in range(count)
    ]


def _repair_sentence_targets(target_chars: int) -> list[int]:
    """Steer repair prose with complete sentences near forty characters each."""

    sentence_count = max(1, (target_chars + 39) // 40)
    return _distribute_integer(target_chars, sentence_count)


def build_server_patch_templates(
    *,
    plan: RepairPlan,
    original_narrative: str,
    contract_hash: str,
) -> list[ServerRepairPatchTemplate]:
    """Freeze all repair authority before a provider can generate prose."""
    original_hash = hashlib.sha256(
        original_narrative.encode("utf-8")
    ).hexdigest()
    preserve = [
        item.text for item in plan.must_preserve_spans if item.text
    ]
    unsupported_ranges: list[tuple[int, int, str]] = []
    seen_unsupported: set[str] = set()
    for item in plan.unsupported_additions:
        evidence = str(item.get("evidence") or "")
        if (
            not evidence
            or evidence in seen_unsupported
            or original_narrative.count(evidence) != 1
        ):
            continue
        seen_unsupported.add(evidence)
        start = original_narrative.find(evidence)
        unsupported_ranges.append((start, start + len(evidence), evidence))

    compact_payloads = compact_patch_templates(
        plan,
        original_narrative,
        base_templates=[],
    )
    compact_ranges: list[tuple[int, int, dict[str, Any]]] = []
    for payload in compact_payloads:
        anchor = payload.get("anchor") or {}
        target = str(anchor.get("start") or anchor.get("before_text") or "")
        if not target or original_narrative.count(target) != 1:
            continue
        start = original_narrative.find(target)
        compact_ranges.append((start, start + len(target), payload))

    deletion_ranges = [
        (start, end)
        for start, end, _ in unsupported_ranges
    ]
    deletion_ranges.extend(
        (start, end) for start, end, _ in compact_ranges
    )
    insertion_offset = _safe_expansion_offset(
        plan,
        original_narrative,
        deletion_ranges=deletion_ranges,
    )

    templates: list[ServerRepairPatchTemplate] = []

    def append_template(
        *,
        patch_type: RepairPatchType,
        insertion: int | None = None,
        start: int | None = None,
        end: int | None = None,
        target_events: list[str] | None = None,
        target_end_states: list[str] | None = None,
        min_chars: int = 0,
        target_chars: int = 0,
        max_chars: int = 300,
        purpose: str = "",
        remove_reason: str = "",
        max_remove_chars: int = 0,
        provider_text_required: bool = False,
        server_patch_text: str | None = None,
        template_preserve: list[str] | None = None,
    ) -> None:
        if len(templates) >= 8:
            return
        targets = [*(target_events or []), *(target_end_states or [])]
        placement = (
            f"insert:{insertion}"
            if insertion is not None
            else f"range:{start}:{end}"
        )
        templates.append(
            ServerRepairPatchTemplate(
                patch_id=_server_patch_id(
                    plan=plan,
                    index=len(templates),
                    patch_type=patch_type,
                    placement=placement,
                    targets=targets,
                ),
                patch_type=patch_type,
                insertion_offset=insertion,
                start_offset=start,
                end_offset=end,
                target_events=target_events or [],
                target_end_states=target_end_states or [],
                min_chars=min_chars,
                target_chars=target_chars,
                max_chars=max_chars,
                preserve=(
                    preserve
                    if template_preserve is None
                    else template_preserve
                ),
                purpose=purpose,
                remove_reason=remove_reason,
                max_remove_chars=max_remove_chars,
                original_narrative_sha256=original_hash,
                contract_hash=contract_hash,
                provider_text_required=provider_text_required,
                server_patch_text=server_patch_text,
            )
        )

    pending_events = [
        *plan.missing_events,
        *plan.incomplete_events,
        *plan.wrong_actor_events,
        *plan.wrong_target_events,
    ]
    for item in pending_events:
        evidence = item.minimum_completion_evidence
        if not evidence:
            continue
        chars = narrative_char_count(evidence)
        if chars > 450:
            raise ValueError("minimum event evidence exceeds repair patch maximum")
        append_template(
            patch_type="insert",
            insertion=insertion_offset,
            target_events=[item.event_id],
            max_chars=max(1, chars),
            server_patch_text=evidence,
        )
    for item in plan.wrong_end_states:
        evidence = item.minimum_completion_evidence
        if not evidence:
            continue
        chars = narrative_char_count(evidence)
        if chars > 450:
            raise ValueError("minimum end-state evidence exceeds repair patch maximum")
        append_template(
            patch_type="insert",
            insertion=insertion_offset,
            target_end_states=[item.state_id],
            max_chars=max(1, chars),
            server_patch_text=evidence,
        )
    for start, end, evidence in unsupported_ranges:
        chars = narrative_char_count(evidence)
        if chars > 300:
            raise ValueError("unsupported addition exceeds local delete maximum")
        append_template(
            patch_type="delete",
            start=start,
            end=end,
            max_chars=max(1, chars),
            server_patch_text="",
            template_preserve=[],
        )
    for start, end, payload in compact_ranges:
        chars = narrative_char_count(original_narrative[start:end])
        append_template(
            patch_type="compact",
            start=start,
            end=end,
            max_chars=max(1, min(450, chars)),
            remove_reason=str(payload.get("remove_reason") or ""),
            max_remove_chars=int(payload.get("max_remove_chars") or chars),
            server_patch_text="",
            template_preserve=[
                str(item) for item in payload.get("preserve", [])
            ],
        )

    projected_delta = sum(
        _template_delta_from_model(item, original_narrative)
        for item in templates
    )
    adjustment = plan.length_adjustment
    original_chars = narrative_char_count(original_narrative)
    if adjustment.current_chars != original_chars:
        raise ValueError(
            "length adjustment current_chars does not match original narrative"
        )
    projected_chars = original_chars + projected_delta
    desired = adjustment.desired_final_chars
    if desired <= 0:
        lower = min(adjustment.max_chars, adjustment.min_chars + 80)
        upper = max(adjustment.min_chars, adjustment.max_chars - 50)
        if lower > upper:
            lower, upper = adjustment.min_chars, adjustment.max_chars
        desired = max(
            lower,
            min(
                lower,
                upper,
            ),
        )
    required_add = max(0, adjustment.min_chars - projected_chars)
    target_add = max(required_add, desired - projected_chars)
    max_add = max(0, adjustment.max_chars - projected_chars)
    if (
        adjustment.action == "add" or required_add > 0
    ) and target_add > 0 and max_add > 0:
        available = max(0, 8 - len(templates))
        requested_target_total = min(max_add, target_add)
        if requested_target_total > 0 and available > 0:
            # Size the request count from the desired addition, then divide the
            # final section headroom across exactly those requests. This freezes
            # a provable aggregate ceiling instead of giving every sibling the
            # independent 450-character cap that overflowed attempt 10.
            chunk_count = max(1, (requested_target_total + 449) // 450)
            chunk_count = min(available, requested_target_total, chunk_count)
            authorized_max_total = min(max_add, 450 * chunk_count)
            if required_add > authorized_max_total:
                # Deterministic templates consumed too many of the eight slots.
                # Return only those server-owned operations and avoid requesting
                # a provider expansion that cannot possibly reach the floor.
                return templates
            centered_target_total = (
                required_add + authorized_max_total
            ) // 2
            generation_target_total = max(
                required_add,
                chunk_count,
                min(requested_target_total, centered_target_total),
            )
            targets = _distribute_integer(
                generation_target_total,
                chunk_count,
            )
            maxima = _distribute_integer(
                authorized_max_total,
                chunk_count,
            )
            minima = _distribute_integer(
                max(required_add, chunk_count),
                chunk_count,
            )
            for minimum, target, maximum in zip(
                minima,
                targets,
                maxima,
                strict=True,
            ):
                append_template(
                    patch_type="expand",
                    insertion=insertion_offset,
                    min_chars=minimum,
                    target_chars=target,
                    max_chars=maximum,
                    purpose=(
                        "expand existing action, environment, interaction, or emotion "
                        "without adding plot or facts"
                    ),
                    provider_text_required=True,
                    server_patch_text=None,
                )
    return templates


def repair_patch_prompt_payload(
    plan: RepairPlan,
    original_narrative: str,
) -> dict[str, Any]:
    templates = plan.patch_templates or build_server_patch_templates(
        plan=plan,
        original_narrative=original_narrative,
        contract_hash=plan.original_contract_hash,
    )
    provider_templates = [
        item for item in templates if item.provider_text_required
    ]
    expansion_focus = (
        "existing action and physical response",
        "existing environment and immediate perception",
        "existing-character interaction and present emotion",
    )
    deterministic_delta = sum(
        _template_delta_from_model(item, original_narrative)
        for item in templates
        if not item.provider_text_required
    )
    projected_without_provider = (
        narrative_char_count(original_narrative) + deterministic_delta
    )
    if plan.length_adjustment.current_chars != narrative_char_count(
        original_narrative
    ):
        raise ValueError(
            "length adjustment current_chars does not match original narrative"
        )
    aggregate_min = max(
        sum(max(1, item.min_chars) for item in provider_templates),
        plan.length_adjustment.min_chars - projected_without_provider,
    )
    aggregate_target = sum(item.target_chars for item in provider_templates)
    aggregate_max = sum(item.max_chars for item in provider_templates)
    final_headroom = max(
        0,
        plan.length_adjustment.max_chars - projected_without_provider,
    )
    if provider_templates and aggregate_max > final_headroom:
        raise ValueError(
            "provider repair template maxima exceed frozen final headroom"
        )
    if provider_templates and aggregate_min > aggregate_max:
        raise ValueError(
            "provider repair templates cannot reach the frozen aggregate floor"
        )
    if provider_templates and not aggregate_min <= aggregate_target <= aggregate_max:
        raise ValueError(
            "provider repair target must stay inside frozen aggregate bounds"
        )
    provider_requests = [
        {
            "patch_id": item.patch_id,
            "min_chars": max(1, item.min_chars),
            "target_chars": item.target_chars,
            "max_chars": item.max_chars,
            "minimum_is_hard": True,
            "target_is_advisory": True,
            "maximum_is_hard": True,
            "drafting_requirement": "mandatory",
            "patch_text_shape": "required_object_cells",
            "cell_names": list(_PROVIDER_REPAIR_CELL_NAMES),
            "cell_count": len(_PROVIDER_REPAIR_CELL_NAMES),
            "cell_target_chars": _distribute_integer(
                item.target_chars,
                len(_PROVIDER_REPAIR_CELL_NAMES),
            ),
            "cell_targets_are_advisory": True,
            "punctuation_included": True,
            "purpose": item.purpose,
            "distinct_focus": expansion_focus[index % len(expansion_focus)],
            "diction": (
                "neutral contemporary literal diction; avoid ornate or classical "
                "number-bearing expressions"
            ),
            "allowed_content": [
                "existing action detail",
                "existing environment",
                "existing-character interaction",
                "existing-character emotion",
            ],
            "forbidden_content": [
                "new event",
                "new character",
                "new fact",
                "new date, number, kinship, injury, casualty, or world rule",
            ],
            "patch_text_lexical_contract": {
                "scope": "patch_text_only",
                "allowed_number_tokens": [],
                "forbidden_pattern": (
                    "[0-9零〇一二两三四五六七八九十百千万]"
                ),
                "includes": [
                    "literal quantity",
                    "rhetorical quantity",
                    "approximate count",
                    "idiom",
                ],
                "number_free_substitutions": [
                    "他们",
                    "些",
                    "少许",
                    "片刻",
                    "反复",
                    "短暂",
                    "微微",
                ],
                "self_check_before_return": True,
                "schema_version_and_patch_id_exempt": True,
            },
        }
        for index, item in enumerate(provider_templates)
    ]
    return {
        "execution_mode": "SERVER_OWNED_TEMPLATE_TEXT_ONLY",
        "provider_patch_requests": provider_requests,
        "server_owned_actions": [
            {
                "patch_id": item.patch_id,
                "patch_type": item.patch_type,
                "provider_text_required": item.provider_text_required,
            }
            for item in templates
        ],
        "expansion_request": (
            provider_requests[0] if provider_requests else None
        ),
        "aggregate_patch_text_budget": (
            {
                "count_non_whitespace_unicode_characters": True,
                "min_chars": aggregate_min,
                "target_chars": aggregate_target,
                "max_chars": aggregate_max,
                "minimum_is_hard": True,
                "target_is_advisory": True,
                "maximum_is_hard": True,
                "uneven_per_patch_allocation_allowed": True,
            }
            if provider_requests
            else None
        ),
        "missing_events": [item.model_dump(mode="json") for item in plan.missing_events],
        "incomplete_events": [item.model_dump(mode="json") for item in plan.incomplete_events],
        "wrong_actor_events": [item.model_dump(mode="json") for item in plan.wrong_actor_events],
        "wrong_target_events": [item.model_dump(mode="json") for item in plan.wrong_target_events],
        "wrong_end_states": [item.model_dump(mode="json") for item in plan.wrong_end_states],
        "unsupported_additions": plan.unsupported_additions,
        "post_resolution_expansions": plan.post_resolution_expansions,
        "preflight_issues": [
            item.model_dump(mode="json") for item in plan.preflight_issues
        ],
        "length_adjustment": plan.length_adjustment.model_dump(mode="json"),
        "must_preserve_spans": [
            {"text": item.text, "reason": item.reason}
            for item in plan.must_preserve_spans
        ],
        "must_preserve_facts": plan.must_preserve_facts,
        "forbidden_changes": plan.forbidden_changes,
        "minimum_style_constraints": (
            [] if provider_requests else plan.style_constraints
        ),
        "instruction": plan.repair_instruction,
        "priority_order": [
            "event_completion",
            "required_end_state",
            "unsupported_addition_delete",
            "length_expand_or_compact",
            *([] if provider_requests else ["style_tiny_adjustment"]),
        ],
        "relevant_windows": _repair_windows(plan, original_narrative),
        "output_contract": {
            "patches": [
                {
                    "patch_id": "copy from provider_patch_requests",
                    "patch_text": {
                        cell_name: "one provider-authored prose beat"
                        for cell_name in _PROVIDER_REPAIR_CELL_NAMES
                    },
                }
            ]
        },
        "final_instruction": (
            "Return schema_version=1 and exactly one patch_id/patch_text pair for "
            "every provider_patch_requests item. Each patch_text must be an object "
            "with exactly beat_1, beat_2, and beat_3; each value must be one complete "
            "developed prose beat. Do not return patch_type, anchor, "
            "offset, targets, target_chars, max_chars, preserve, purpose, hashes, "
            "state, threads, memory, or full narrative. Never repeat source prose "
            "and never create plot or facts. The server joins each patch_text object's "
            "three values verbatim; every joined patch must stay within its own hard "
            "min_chars and max_chars. Per-request target_chars is advisory: uneven "
            "distribution is allowed only within every request's frozen band. The "
            "total non-whitespace "
            "patch_text length must stay within aggregate_patch_text_budget min_chars "
            "and max_chars; aim near its target_chars. The supplied cell_target_chars "
            "are mandatory drafting steering: write one complete developed beat per "
            "cell, counting punctuation, rather than a fragment or terse summary. "
            "Use neutral contemporary "
            "literal diction rather than style ornament. Before returning, self-scan "
            "each patch_text beat and ensure it contains no glyph matched by "
            "[0-9零〇一二两三四五六七八九十百千万], even in rhetoric, "
            "approximate counts, or idioms; schema_version and patch_id are exempt."
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
    "PreflightRepairIssue",
    "RepairEndStateInstruction",
    "RepairEventInstruction",
    "RepairPatchType",
    "RepairPlan",
    "RepairPlanBuilder",
    "RepairPreserveSpan",
    "RepairRegressionValidator",
    "ServerRepairPatchTemplate",
    "build_server_patch_templates",
    "compact_patch_templates",
    "repair_patch_prompt_payload",
    "repair_plan_prompt_payload",
]
