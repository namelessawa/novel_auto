"""Deterministic, local prose patches for the one-shot Repair boundary."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from story.event_execution import EventExecutionPlan
from story.narrative_contract import NarrativeContract, NarrativeModel
from story.repair_plan import RepairPlan


PatchType = Literal["insert", "replace", "delete"]


class RepairPatchAnchor(NarrativeModel):
    """Exact prose surrounding a local edit.

    INSERT inserts after ``before_text`` (or before ``after_text`` when no
    before anchor exists).  REPLACE/DELETE edit the text between two anchors;
    with only one anchor, that anchor itself is the edit target.
    """

    before_text: str = Field(default="", max_length=240)
    after_text: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def require_anchor(self) -> "RepairPatchAnchor":
        if not self.before_text and not self.after_text:
            raise ValueError("at least one exact anchor is required")
        return self


class RepairPatch(NarrativeModel):
    patch_type: PatchType
    anchor: RepairPatchAnchor
    patch_text: str = Field(default="", max_length=600)
    target_events: list[str] = Field(default_factory=list)
    target_end_states: list[str] = Field(default_factory=list)
    max_chars: int = Field(default=300, ge=1, le=300)
    preserve: list[str] = Field(default_factory=list)


class RepairPatchSet(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    patches: list[RepairPatch] = Field(default_factory=list, max_length=8)


class RepairPatchViolation(NarrativeModel):
    code: str
    message: str
    patch_index: int = Field(default=-1, ge=-1)
    evidence: str = ""


class RepairPatchValidationReport(NarrativeModel):
    accepted: bool = False
    violations: list[RepairPatchViolation] = Field(default_factory=list)
    patch_count: int = Field(default=0, ge=0)
    applied_count: int = Field(default=0, ge=0)
    original_sha256: str = ""
    final_sha256: str = ""
    char_delta: int = 0


class RepairPatchApplyResult(NarrativeModel):
    narrative_text: str
    report: RepairPatchValidationReport


@dataclass(frozen=True)
class _ResolvedPatch:
    start: int
    end: int
    target_text: str


_KINSHIP = re.compile(
    r"父亲|母亲|祖父|祖母|爷爷|奶奶|外祖父|外祖母|兄长|哥哥|弟弟|"
    r"姐姐|妹妹|儿子|女儿|丈夫|妻子|舅舅|姑姑|姨母"
)
_DATE = re.compile(
    r"\d{4}年(?:\d{1,2}月(?:\d{1,2}日)?)?|"
    r"[一二三四五六七八九十]+月[一二三四五六七八九十]+日"
)
_CASUALTY = re.compile(
    r"(?:\d+|[零〇一二两三四五六七八九十百千万]+)"
    r"(?:条|名|个|位)?(?:人命|人死亡|人丧生|人遇难)"
)
_NUMBER = re.compile(r"\d+|[零〇一二两三四五六七八九十百千万]+")
_INJURY = re.compile(r"骨折|中弹|刺伤|重伤|轻伤|流血|伤口")
_BACKSTORY = re.compile(
    r"(?:小时候|童年|多年前|曾经|原来|其实).{0,24}"
    r"(?:来自|经历|身份|家族|加入|服役|认识)"
)
_WORLD_RULE = re.compile(
    r"(?:从此|今后|在这个世界|世界上).{0,24}"
    r"(?:必须|永远|不能|可以|规则|法则)"
)
_STORY_THREAD = re.compile(
    r"(?:另一条|新的|另有|还藏着).{0,16}(?:线索|任务|秘密|阴谋|支线)"
)
_NEW_CHARACTER = re.compile(
    r"(?:名叫|叫作|自称)([\u3400-\u9fff]{2,5})|"
    r"(?:一个|一名|那名)([\u3400-\u9fff]{1,8}(?:人|水手|工人|医生|警官|调查员))"
)
_POSSESSION = (
    "接过",
    "收下",
    "收好",
    "保管",
    "持有",
    "放进",
    "塞进",
    "藏进",
    "藏好",
    "纳入",
    "贴胸藏",
    "握住",
    "拿着",
)


def _nonspace_chars(text: str) -> int:
    return sum(not char.isspace() for char in text)


def _occurrences(text: str, needle: str) -> list[int]:
    if not needle:
        return []
    positions: list[int] = []
    start = 0
    while True:
        found = text.find(needle, start)
        if found < 0:
            return positions
        positions.append(found)
        start = found + 1


def _resolve_patch(text: str, patch: RepairPatch) -> tuple[_ResolvedPatch | None, str]:
    before = patch.anchor.before_text
    after = patch.anchor.after_text
    if before and after:
        pairs: list[tuple[int, int]] = []
        after_positions = _occurrences(text, after)
        for before_pos in _occurrences(text, before):
            before_end = before_pos + len(before)
            following = [position for position in after_positions if position >= before_end]
            if following:
                pairs.append((before_end, min(following)))
        if not pairs:
            return None, "PATCH_ANCHOR_NOT_FOUND"
        if len(set(pairs)) != 1:
            return None, "PATCH_ANCHOR_AMBIGUOUS"
        between_start, between_end = pairs[0]
        if patch.patch_type == "insert":
            return _ResolvedPatch(between_start, between_start, ""), ""
        return (
            _ResolvedPatch(
                between_start,
                between_end,
                text[between_start:between_end],
            ),
            "",
        )

    anchor = before or after
    positions = _occurrences(text, anchor)
    if not positions:
        return None, "PATCH_ANCHOR_NOT_FOUND"
    if len(positions) != 1:
        return None, "PATCH_ANCHOR_AMBIGUOUS"
    position = positions[0]
    if patch.patch_type == "insert":
        insertion = position + len(anchor) if before else position
        return _ResolvedPatch(insertion, insertion, ""), ""
    return _ResolvedPatch(position, position + len(anchor), anchor), ""


def _entity_names(contract: NarrativeContract, identifier: str) -> list[str]:
    for group in (
        contract.allowed_entities.characters,
        contract.allowed_entities.locations,
        contract.allowed_entities.items,
        contract.allowed_entities.organizations,
    ):
        for entity in group:
            if identifier in entity.all_names:
                return [name for name in entity.all_names if name]
    return [identifier] if identifier else []


def _authorized_numbers(plan: RepairPlan, original_text: str) -> set[str]:
    payload = [
        original_text,
        *[
            f"{item.action} {item.minimum_completion_evidence}"
            for item in [
                *plan.missing_events,
                *plan.incomplete_events,
                *plan.wrong_actor_events,
                *plan.wrong_target_events,
            ]
        ],
        *[
            f"{item.path} {item.expected} {item.minimum_completion_evidence}"
            for item in plan.wrong_end_states
        ],
    ]
    return set(_NUMBER.findall(" ".join(payload)))


def _authorized_repair_text(plan: RepairPlan) -> str:
    return " ".join(
        [
            *[
                f"{item.action} {item.minimum_completion_evidence}"
                for item in [
                    *plan.missing_events,
                    *plan.incomplete_events,
                    *plan.wrong_actor_events,
                    *plan.wrong_target_events,
                ]
            ],
            *[
                item.minimum_completion_evidence
                for item in plan.wrong_end_states
            ],
        ]
    )


class RepairPatchValidator:
    """Validate and apply a bounded patch set without prose-generation authority."""

    def validate_and_apply(
        self,
        *,
        original_text: str,
        patch_set: RepairPatchSet,
        plan: RepairPlan,
        contract: NarrativeContract,
        event_plan: EventExecutionPlan,
    ) -> RepairPatchApplyResult:
        text = original_text
        original_hash = hashlib.sha256(original_text.encode("utf-8")).hexdigest()
        violations: list[RepairPatchViolation] = []
        applied_count = 0
        allowed_events = {
            item.event_id
            for item in [
                *plan.missing_events,
                *plan.incomplete_events,
                *plan.wrong_actor_events,
                *plan.wrong_target_events,
            ]
        }
        allowed_end_states = {item.state_id for item in plan.wrong_end_states}
        plan_events = {
            item.id: item
            for item in event_plan.ordered_events
            if item.id in allowed_events
        }
        plan_end_states = {
            item.state_id: item for item in plan.wrong_end_states
        }
        unsupported_evidence = {
            str(item.get("evidence") or "")
            for item in plan.unsupported_additions
            if item.get("evidence")
        }
        authorized_numbers = _authorized_numbers(plan, original_text)
        authorized_repair_text = _authorized_repair_text(plan)
        length_authorized = plan.length_adjustment.action != "none"
        allowed_character_names = {
            name
            for entity in contract.allowed_entities.characters
            for name in entity.all_names
        }

        if not patch_set.patches:
            violations.append(
                RepairPatchViolation(
                    code="REPAIR_NO_CHANGE",
                    message="Repair 没有返回任何局部 patch",
                )
            )

        for index, patch in enumerate(patch_set.patches):
            resolved, anchor_error = _resolve_patch(text, patch)
            if anchor_error:
                violations.append(
                    RepairPatchViolation(
                        code=anchor_error,
                        message="Patch anchor 必须在当前正文中唯一匹配",
                        patch_index=index,
                        evidence=(
                            patch.anchor.before_text or patch.anchor.after_text
                        )[:180],
                    )
                )
                continue
            assert resolved is not None

            patch_errors: list[RepairPatchViolation] = []

            def add(code: str, message: str, evidence: str = "") -> None:
                patch_errors.append(
                    RepairPatchViolation(
                        code=code,
                        message=message,
                        patch_index=index,
                        evidence=evidence[:180],
                    )
                )

            if patch.patch_type == "delete" and patch.patch_text:
                add("PATCH_DELETE_HAS_TEXT", "DELETE patch_text 必须为空")
            if patch.patch_type != "delete" and not patch.patch_text.strip():
                add("PATCH_TEXT_EMPTY", "INSERT/REPLACE 必须提供 patch_text")
            if _nonspace_chars(patch.patch_text) > patch.max_chars:
                add(
                    "PATCH_TOO_LONG",
                    f"Patch 超过 {patch.max_chars} 字",
                    patch.patch_text,
                )
            if _nonspace_chars(resolved.target_text) > 300:
                add(
                    "PATCH_SCOPE_TOO_LARGE",
                    "REPLACE/DELETE 的原文目标超过 300 字",
                    resolved.target_text,
                )
            if (
                patch.patch_type in {"replace", "delete"}
                and resolved.target_text.strip() == text.strip()
            ):
                add(
                    "PATCH_SCOPE_TOO_LARGE",
                    "Patch 不得替换或删除整篇正文",
                    resolved.target_text,
                )

            unknown_events = set(patch.target_events) - allowed_events
            unknown_states = set(patch.target_end_states) - allowed_end_states
            if unknown_events or unknown_states:
                add(
                    "PATCH_TARGET_NOT_IN_PLAN",
                    "Patch 只能处理 RepairPlan 明确列出的事件和终态",
                    ",".join(sorted(unknown_events | unknown_states)),
                )

            delete_authorized = (
                patch.patch_type == "delete"
                and any(
                    evidence in resolved.target_text
                    for evidence in unsupported_evidence
                )
            )
            if (
                not patch.target_events
                and not patch.target_end_states
                and not delete_authorized
                and not length_authorized
            ):
                add(
                    "PATCH_PURPOSE_NOT_AUTHORIZED",
                    "Patch 必须指向一个待修事件、待修终态或明确的未授权新增",
                    resolved.target_text,
                )

            for preserved in plan.must_preserve_spans:
                if (
                    not preserved.text
                    or patch.patch_type == "insert"
                    or delete_authorized
                ):
                    continue
                preserved_start = text.find(preserved.text)
                if preserved_start < 0:
                    continue
                preserved_end = preserved_start + len(preserved.text)
                if (
                    resolved.start < preserved_end
                    and resolved.end > preserved_start
                ):
                    add(
                        "REPAIR_REGRESSION",
                        f"Patch 试图修改已通过内容: {preserved.reason}",
                        preserved.text,
                    )

            if patch.patch_type != "delete":
                kinship = _KINSHIP.search(patch.patch_text)
                if kinship:
                    add(
                        "PATCH_ADDS_KINSHIP",
                        "Patch 不得新增亲属关系",
                        kinship.group(0),
                    )
                date = _DATE.search(patch.patch_text)
                if date and date.group(0) not in original_text:
                    add("PATCH_ADDS_DATE", "Patch 不得新增日期", date.group(0))
                casualty = _CASUALTY.search(patch.patch_text)
                if casualty and casualty.group(0) not in original_text:
                    add(
                        "PATCH_ADDS_CASUALTY",
                        "Patch 不得新增伤亡数字",
                        casualty.group(0),
                    )
                injury = _INJURY.search(patch.patch_text)
                if (
                    injury
                    and injury.group(0) not in original_text
                    and injury.group(0) not in authorized_repair_text
                ):
                    add(
                        "PATCH_ADDS_INJURY",
                        "Patch 不得新增伤势",
                        injury.group(0),
                    )
                backstory = _BACKSTORY.search(patch.patch_text)
                if (
                    backstory
                    and backstory.group(0) not in original_text
                    and backstory.group(0) not in authorized_repair_text
                ):
                    add(
                        "PATCH_ADDS_BACKSTORY",
                        "Patch 不得新增人物背景",
                        backstory.group(0),
                    )
                world_rule = _WORLD_RULE.search(patch.patch_text)
                if (
                    world_rule
                    and world_rule.group(0) not in original_text
                    and world_rule.group(0) not in authorized_repair_text
                ):
                    add(
                        "PATCH_ADDS_WORLD_RULE",
                        "Patch 不得新增世界规则",
                        world_rule.group(0),
                    )
                story_thread = _STORY_THREAD.search(patch.patch_text)
                if (
                    story_thread
                    and story_thread.group(0) not in original_text
                    and story_thread.group(0) not in authorized_repair_text
                ):
                    add(
                        "PATCH_ADDS_STORY_THREAD",
                        "Patch 不得新增故事线",
                        story_thread.group(0),
                    )
                for number in _NUMBER.findall(patch.patch_text):
                    if number not in authorized_numbers:
                        add(
                            "PATCH_ADDS_NUMBER",
                            "Patch 不得新增 RepairPlan 未授权的数字",
                            number,
                        )
                        break
                new_character = _NEW_CHARACTER.search(patch.patch_text)
                if new_character:
                    name = next(
                        (
                            value
                            for value in new_character.groups()
                            if value
                        ),
                        "",
                    )
                    if name not in allowed_character_names:
                        add(
                            "PATCH_ADDS_CHARACTER",
                            "Patch 不得新增人物",
                            new_character.group(0),
                        )

            for event_id in patch.target_events:
                planned = plan_events.get(event_id)
                if planned is None:
                    continue
                actor_ok = not planned.actor_aliases or any(
                    name in patch.patch_text for name in planned.actor_aliases
                )
                target_ok = not planned.target_aliases or any(
                    name in patch.patch_text for name in planned.target_aliases
                )
                if not actor_ok or not target_ok:
                    add(
                        "PATCH_EVENT_EVIDENCE_INCOMPLETE",
                        "事件 Patch 必须明确写出 actor 和 target",
                        patch.patch_text,
                    )

            for state_id in patch.target_end_states:
                state = plan_end_states.get(state_id)
                if state is None:
                    continue
                parts = [part for part in state.path.split("/") if part]
                expected_names = _entity_names(contract, str(state.expected))
                if parts and parts[-1] in {"holder", "owner", "owners"}:
                    item_names = (
                        _entity_names(contract, parts[-2])
                        if len(parts) >= 2
                        else []
                    )
                    expected_ok = not expected_names or any(
                        name in patch.patch_text for name in expected_names
                    )
                    item_ok = not item_names or any(
                        name in patch.patch_text for name in item_names
                    )
                    possession_ok = any(
                        term in patch.patch_text for term in _POSSESSION
                    )
                    if not (expected_ok and item_ok and possession_ok):
                        add(
                            "PATCH_END_STATE_EVIDENCE_INCOMPLETE",
                            "终态 Patch 必须明确写出持有人、物品和完成后的持有动作",
                            patch.patch_text,
                        )

            violations.extend(patch_errors)
            if patch_errors:
                continue

            replacement = "" if patch.patch_type == "delete" else patch.patch_text
            text = text[: resolved.start] + replacement + text[resolved.end :]
            if any(span and span not in text for span in patch.preserve):
                violations.append(
                    RepairPatchViolation(
                        code="REPAIR_REGRESSION",
                        message="Patch 删除了自身声明必须保留的正文",
                        patch_index=index,
                    )
                )
                continue
            applied_count += 1

        final_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if not violations and final_hash == original_hash:
            violations.append(
                RepairPatchViolation(
                    code="REPAIR_NO_CHANGE",
                    message="应用 Patch 后正文 hash 未变化",
                )
            )
        report = RepairPatchValidationReport(
            accepted=not violations,
            violations=violations,
            patch_count=len(patch_set.patches),
            applied_count=applied_count,
            original_sha256=original_hash,
            final_sha256=final_hash,
            char_delta=_nonspace_chars(text) - _nonspace_chars(original_text),
        )
        return RepairPatchApplyResult(
            narrative_text=text if report.accepted else original_text,
            report=report,
        )


__all__ = [
    "PatchType",
    "RepairPatch",
    "RepairPatchAnchor",
    "RepairPatchApplyResult",
    "RepairPatchSet",
    "RepairPatchValidationReport",
    "RepairPatchValidator",
    "RepairPatchViolation",
]
