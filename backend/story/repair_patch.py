"""Deterministic, local prose patches for the one-shot Repair boundary."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from pydantic import ConfigDict, Field, model_validator

from story.event_execution import EventExecutionPlan
from story.narrative_contract import NarrativeContract, NarrativeModel
from story.repair_plan import (
    RepairPatchType,
    RepairPlan,
    ServerRepairPatchTemplate,
    compact_patch_templates,
)


PatchType = RepairPatchType


class RepairPatchAnchor(NarrativeModel):
    """Exact prose surrounding a local edit.

    INSERT inserts after ``before_text`` (or before ``after_text`` when no
    before anchor exists).  REPLACE/DELETE edit the text between two anchors;
    with only one anchor, that anchor itself is the edit target.
    """

    before_text: str = Field(default="", max_length=240)
    after_text: str = Field(default="", max_length=240)
    start: str = Field(default="", max_length=240)
    end: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def require_anchor(self) -> "RepairPatchAnchor":
        if not any((self.before_text, self.after_text, self.start, self.end)):
            raise ValueError("at least one exact anchor is required")
        if self.before_text and self.start:
            raise ValueError("anchor cannot use both before_text and start")
        if self.after_text and self.end:
            raise ValueError("anchor cannot use both after_text and end")
        return self


class RepairPatch(NarrativeModel):
    patch_id: str = Field(default="", max_length=128)
    patch_type: PatchType
    anchor: RepairPatchAnchor | None = None
    insertion_offset: int | None = Field(default=None, ge=0)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    patch_text: str = Field(default="", max_length=900)
    target_events: list[str] = Field(default_factory=list)
    target_end_states: list[str] = Field(default_factory=list)
    max_chars: int = Field(default=300, ge=1, le=450)
    preserve: list[str] = Field(default_factory=list)
    target_chars: int = Field(default=0, ge=0, le=450)
    purpose: str = Field(default="", max_length=240)
    remove_reason: str = Field(default="", max_length=240)
    max_remove_chars: int = Field(default=0, ge=0, le=300)
    original_narrative_sha256: str = Field(default="", max_length=64)
    contract_hash: str = ""

    @model_validator(mode="after")
    def require_anchor_or_frozen_offset(self) -> "RepairPatch":
        if self.patch_type in {"insert", "expand"}:
            if self.anchor is None and self.insertion_offset is None:
                raise ValueError("insert/expand requires an anchor or frozen offset")
        elif self.anchor is None and (
            self.start_offset is None or self.end_offset is None
        ):
            raise ValueError("replace/delete/compact requires an anchor or frozen range")
        return self


class RepairPatchSet(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    patches: list[RepairPatch] = Field(default_factory=list, max_length=8)


class ProviderRepairPatch(NarrativeModel):
    """The complete provider authority for one repair response."""

    patch_id: str = Field(min_length=1, max_length=128)
    patch_text: str = Field(max_length=900)


class ProviderRepairPatchSet(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    patches: list[ProviderRepairPatch] = Field(default_factory=list, max_length=8)


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
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    narrative_text: str
    report: RepairPatchValidationReport
    applied_patches: RepairPatchSet = Field(default_factory=RepairPatchSet)
    enforced_removals: list[dict[str, str]] = Field(default_factory=list)


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
_APPROXIMATE_PARTICLE_COUNT = re.compile(r"一两(?:颗|粒)")
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
_CLASSICAL_HISTORY = re.compile(
    r"朝代|王朝|年号|官职|官衔|世家|宗族|家谱|前朝|本朝|开国|皇帝|丞相|太守"
)
_EXPAND_PURPOSE = (
    "expand existing action, environment, interaction, or emotion "
    "without adding plot or facts"
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
    if patch.patch_type in {"insert", "expand"} and patch.insertion_offset is not None:
        if patch.insertion_offset > len(text):
            return None, "PATCH_OFFSET_OUT_OF_RANGE"
        return (
            _ResolvedPatch(
                patch.insertion_offset,
                patch.insertion_offset,
                "",
            ),
            "",
        )
    if (
        patch.patch_type not in {"insert", "expand"}
        and patch.start_offset is not None
        and patch.end_offset is not None
    ):
        if (
            patch.start_offset > patch.end_offset
            or patch.end_offset > len(text)
        ):
            return None, "PATCH_OFFSET_OUT_OF_RANGE"
        return (
            _ResolvedPatch(
                patch.start_offset,
                patch.end_offset,
                text[patch.start_offset : patch.end_offset],
            ),
            "",
        )
    if patch.anchor is None:
        return None, "PATCH_PLACEMENT_MISSING"
    before = patch.anchor.before_text or patch.anchor.start
    after = patch.anchor.after_text or patch.anchor.end
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
        if patch.patch_type in {"insert", "expand"}:
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
    if patch.patch_type in {"insert", "expand"}:
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


def _normalize_expand_particle_count(
    patch: RepairPatch,
    *,
    patch_index: int,
    authorized_numbers: set[str],
) -> tuple[RepairPatch, list[dict[str, str]]]:
    """Remove one narrow non-canonical particle count without weakening gates.

    The original provider patch remains persisted on the transaction.  This
    normalization only removes the approximate ``一两颗/一两粒`` quantity from
    an EXPAND patch, records the exact edit, and then sends the resulting patch
    through every existing deterministic patch and narrative validator.
    """
    if patch.patch_type != "expand" or "一两" in authorized_numbers:
        return patch, []
    removals: list[dict[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        removals.append(
            {
                "patch_index": str(patch_index),
                "code": "PATCH_APPROXIMATE_PARTICLE_COUNT_REMOVED",
                "removed": match.group(0),
                "replacement": "些",
            }
        )
        return "些"

    normalized = _APPROXIMATE_PARTICLE_COUNT.sub(replace, patch.patch_text)
    if not removals:
        return patch, []
    return patch.model_copy(update={"patch_text": normalized}), removals


def _template_patch(
    template: ServerRepairPatchTemplate,
    *,
    patch_text: str,
) -> RepairPatch:
    return RepairPatch(
        patch_id=template.patch_id,
        patch_type=template.patch_type,
        insertion_offset=template.insertion_offset,
        start_offset=template.start_offset,
        end_offset=template.end_offset,
        patch_text=patch_text,
        target_events=template.target_events,
        target_end_states=template.target_end_states,
        max_chars=template.max_chars,
        preserve=template.preserve,
        target_chars=template.target_chars,
        purpose=template.purpose,
        remove_reason=template.remove_reason,
        max_remove_chars=template.max_remove_chars,
        original_narrative_sha256=template.original_narrative_sha256,
        contract_hash=template.contract_hash,
    )


def _bound_apply_order(
    indexed_patch: tuple[int, RepairPatch],
) -> tuple[int, int, int]:
    index, patch = indexed_patch
    placement = (
        patch.insertion_offset
        if patch.insertion_offset is not None
        else patch.start_offset
        if patch.start_offset is not None
        else -1
    )
    # For inserts at one frozen boundary, applying terminal evidence first,
    # event evidence second, and expansion last yields final prose ordered as
    # expansion -> event -> terminal state.
    same_offset_rank = (
        3
        if patch.target_end_states
        else 2
        if patch.target_events
        else 1
        if patch.patch_type == "expand"
        else 0
    )
    return placement, same_offset_rank, index


def _bind_server_templates(
    *,
    templates: list[ServerRepairPatchTemplate],
    provider_patch_set: ProviderRepairPatchSet,
) -> tuple[RepairPatchSet, list[RepairPatchViolation]]:
    violations: list[RepairPatchViolation] = []
    required = {
        item.patch_id: item
        for item in templates
        if item.provider_text_required
    }
    returned_ids = [item.patch_id for item in provider_patch_set.patches]
    seen: set[str] = set()
    for index, patch_id in enumerate(returned_ids):
        if patch_id in seen:
            violations.append(
                RepairPatchViolation(
                    code="PATCH_ID_DUPLICATE",
                    message="Provider 重复返回同一个 patch_id",
                    patch_index=index,
                    evidence=patch_id,
                )
            )
        seen.add(patch_id)
        if patch_id not in required:
            violations.append(
                RepairPatchViolation(
                    code="PATCH_ID_UNKNOWN",
                    message="Provider 返回了服务端未请求的 patch_id",
                    patch_index=index,
                    evidence=patch_id,
                )
            )
    for missing in sorted(set(required) - set(returned_ids)):
        violations.append(
            RepairPatchViolation(
                code="PATCH_ID_MISSING",
                message="Provider 未返回服务端要求的 patch_id",
                evidence=missing,
            )
        )
    if violations:
        return RepairPatchSet(), violations

    provider_text = {
        item.patch_id: item.patch_text
        for item in provider_patch_set.patches
    }
    bound = [
        _template_patch(
            template,
            patch_text=(
                provider_text[template.patch_id]
                if template.provider_text_required
                else template.server_patch_text or ""
            ),
        )
        for template in templates
    ]
    indexed = list(enumerate(bound))
    indexed.sort(key=_bound_apply_order, reverse=True)
    return RepairPatchSet(patches=[item for _, item in indexed]), []


class RepairPatchValidator:
    """Validate and apply a bounded patch set without prose-generation authority."""

    def validate_and_apply(
        self,
        *,
        original_text: str,
        patch_set: RepairPatchSet | None,
        provider_patch_set: ProviderRepairPatchSet | None = None,
        plan: RepairPlan,
        contract: NarrativeContract,
        event_plan: EventExecutionPlan,
    ) -> RepairPatchApplyResult:
        text = original_text
        original_hash = hashlib.sha256(original_text.encode("utf-8")).hexdigest()
        violations: list[RepairPatchViolation] = []
        enforced_removals: list[dict[str, str]] = []
        applied_count = 0
        templates = plan.patch_templates
        server_template_mode = bool(templates and patch_set is None)
        if server_template_mode:
            authority_errors: list[RepairPatchViolation] = []
            for index, template in enumerate(templates):
                if template.original_narrative_sha256 != original_hash:
                    authority_errors.append(
                        RepairPatchViolation(
                            code="ORIGINAL_NARRATIVE_HASH_MISMATCH",
                            message="原正文 hash 与冻结 Repair 模板不一致",
                            patch_index=index,
                            evidence=template.patch_id,
                        )
                    )
                if template.contract_hash != contract.contract_hash:
                    authority_errors.append(
                        RepairPatchViolation(
                            code="REPAIR_CONTRACT_HASH_MISMATCH",
                            message="NarrativeContract hash 与冻结 Repair 模板不一致",
                            patch_index=index,
                            evidence=template.patch_id,
                        )
                    )
            if authority_errors:
                report = RepairPatchValidationReport(
                    accepted=False,
                    violations=authority_errors,
                    patch_count=len(templates),
                    applied_count=0,
                    original_sha256=original_hash,
                    final_sha256=original_hash,
                    char_delta=0,
                )
                return RepairPatchApplyResult(
                    narrative_text=original_text,
                    report=report,
                )
            patch_set, bind_errors = _bind_server_templates(
                templates=templates,
                provider_patch_set=(
                    provider_patch_set or ProviderRepairPatchSet()
                ),
            )
            if bind_errors:
                report = RepairPatchValidationReport(
                    accepted=False,
                    violations=bind_errors,
                    patch_count=len(templates),
                    applied_count=0,
                    original_sha256=original_hash,
                    final_sha256=original_hash,
                    char_delta=0,
                )
                return RepairPatchApplyResult(
                    narrative_text=original_text,
                    report=report,
                )
        patch_set = patch_set or RepairPatchSet()
        template_by_id = {
            item.patch_id: item for item in templates
        }
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
        authorized_compacts = compact_patch_templates(plan, original_text)
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

        for index, provider_patch in enumerate(patch_set.patches):
            patch, patch_removals = _normalize_expand_particle_count(
                provider_patch,
                patch_index=index,
                authorized_numbers=authorized_numbers,
            )
            enforced_removals.extend(patch_removals)
            resolved, anchor_error = _resolve_patch(text, patch)
            if anchor_error:
                violations.append(
                    RepairPatchViolation(
                        code=anchor_error,
                        message="Patch anchor 必须在当前正文中唯一匹配",
                        patch_index=index,
                        evidence=(
                            (
                                patch.anchor.before_text
                                or patch.anchor.after_text
                            )
                            if patch.anchor is not None
                            else patch.patch_id
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

            if patch.patch_type in {"delete", "compact"} and patch.patch_text:
                add(
                    "PATCH_DELETE_HAS_TEXT"
                    if patch.patch_type == "delete"
                    else "PATCH_COMPACT_HAS_TEXT",
                    "DELETE/COMPACT patch_text 必须为空",
                )
            if patch.patch_type not in {"delete", "compact"} and not patch.patch_text.strip():
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
                patch.patch_type in {"replace", "delete", "compact"}
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

            if patch.patch_type == "expand":
                actual_chars = _nonspace_chars(patch.patch_text)
                frozen_template = (
                    template_by_id.get(patch.patch_id)
                    if server_template_mode
                    else None
                )
                if frozen_template is not None:
                    allowed_min = frozen_template.min_chars
                    allowed_target = frozen_template.target_chars
                    allowed_max = frozen_template.max_chars
                else:
                    allowed_min = 0
                    allowed_target = min(
                        450,
                        max(
                            0,
                            (
                                plan.length_adjustment.desired_final_chars
                                or plan.length_adjustment.min_chars
                            )
                            - _nonspace_chars(text),
                        ),
                    )
                    allowed_max = min(
                        450,
                        max(
                            0,
                            plan.length_adjustment.max_chars
                            - _nonspace_chars(text),
                        ),
                    )
                length_add_authorized = (
                    plan.length_adjustment.action == "add"
                    or (
                        server_template_mode
                        and frozen_template is not None
                        and frozen_template.provider_text_required
                    )
                )
                if not length_add_authorized:
                    add("EXPAND_NOT_AUTHORIZED", "RepairPlan 未授权长度扩写")
                if patch.target_events or patch.target_end_states:
                    add(
                        "EXPAND_TARGET_FORBIDDEN",
                        "EXPAND 不能承担新事件或终态变更",
                    )
                if patch.purpose != _EXPAND_PURPOSE:
                    add(
                        "EXPAND_PURPOSE_MISMATCH",
                        "EXPAND purpose 必须逐字匹配服务端计划",
                        patch.purpose,
                    )
                authority_mismatch = (
                    patch.target_chars != allowed_target
                    or patch.max_chars != allowed_max
                    if frozen_template is not None
                    else patch.target_chars > allowed_target
                    or patch.max_chars > allowed_max
                )
                if (
                    patch.target_chars <= 0
                    or patch.max_chars < patch.target_chars
                    or authority_mismatch
                ):
                    add(
                        "EXPAND_TARGET_TOO_LARGE",
                        "EXPAND target/max chars 超过服务端授权范围",
                        f"{patch.target_chars}/{patch.max_chars}",
                    )
                if actual_chars > patch.max_chars:
                    add(
                        "EXPAND_TOO_LARGE",
                        "EXPAND 正文超过 max_chars",
                        str(actual_chars),
                    )
                minimum_patch_chars = (
                    allowed_min
                    if frozen_template is not None and allowed_min > 0
                    else max(1, int(patch.target_chars * 0.6))
                )
                if actual_chars < minimum_patch_chars:
                    add(
                        "EXPAND_TOO_SMALL",
                        "EXPAND 正文未达到服务端冻结下限",
                        str(actual_chars),
                    )
                if patch.patch_text.strip() in original_text:
                    add(
                        "EXPAND_REPEATS_SOURCE",
                        "EXPAND 不得复制或重复已有正文",
                        patch.patch_text,
                    )
                if patch.remove_reason or patch.max_remove_chars:
                    add(
                        "EXPAND_COMPACT_FIELDS_FORBIDDEN",
                        "EXPAND 不能携带 COMPACT 字段",
                    )
            elif patch.patch_type == "compact":
                if server_template_mode and patch.patch_id in template_by_id:
                    authorized = True
                else:
                    if patch.anchor is None:
                        authorized = False
                        effective_anchor = {"start": "", "end": ""}
                    else:
                        effective_anchor = {
                            "start": (
                                patch.anchor.start
                                or patch.anchor.before_text
                            ),
                            "end": (
                                patch.anchor.end
                                or patch.anchor.after_text
                            ),
                        }
                    authorized = any(
                        effective_anchor
                        == {
                            "start": str(
                                (item.get("anchor") or {}).get("start") or ""
                            ),
                            "end": str(
                                (item.get("anchor") or {}).get("end") or ""
                            ),
                        }
                        and patch.remove_reason == item.get("remove_reason")
                        and patch.max_remove_chars == item.get("max_remove_chars")
                        and patch.preserve == item.get("preserve")
                        for item in authorized_compacts
                    )
                if not authorized:
                    add(
                        "COMPACT_NOT_AUTHORIZED",
                        "COMPACT 必须逐字段匹配服务端可删除片段",
                        resolved.target_text,
                    )
                if patch.target_events or patch.target_end_states:
                    add(
                        "COMPACT_TARGET_FORBIDDEN",
                        "COMPACT 不能承担事件或终态修改",
                    )
                if patch.target_chars or patch.purpose:
                    add(
                        "COMPACT_EXPAND_FIELDS_FORBIDDEN",
                        "COMPACT 不能携带 EXPAND 字段",
                    )
                removed_chars = _nonspace_chars(resolved.target_text)
                if patch.max_remove_chars <= 0 or removed_chars > patch.max_remove_chars:
                    add(
                        "COMPACT_TOO_LARGE",
                        "COMPACT 删除量超过服务端上限",
                        str(removed_chars),
                    )
            elif patch.target_chars or patch.purpose:
                add(
                    "PATCH_EXPAND_FIELDS_FORBIDDEN",
                    "只有 EXPAND 可以携带 target_chars 与 purpose",
                )
            elif patch.remove_reason or patch.max_remove_chars:
                add(
                    "PATCH_COMPACT_FIELDS_FORBIDDEN",
                    "只有 COMPACT 可以携带 remove_reason 与 max_remove_chars",
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
                and not (
                    patch.patch_type == "expand"
                    and (
                        frozen_template is not None
                        or _nonspace_chars(text)
                        < plan.length_adjustment.min_chars
                    )
                )
                and patch.patch_type != "compact"
            ):
                add(
                    "PATCH_PURPOSE_NOT_AUTHORIZED",
                    "Patch 必须指向一个待修事件、待修终态或明确的未授权新增",
                    resolved.target_text,
                )

            for preserved in plan.must_preserve_spans:
                if (
                    not preserved.text
                    or patch.patch_type in {"insert", "expand"}
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
                style_key = str(plan.style_constraints.get("key") or "")
                classical_history = _CLASSICAL_HISTORY.search(patch.patch_text)
                if style_key == "classical_chapter" and classical_history:
                    add(
                        "PATCH_ADDS_HISTORY",
                        "古典章回扩写不得新增历史、朝代、家族或官职背景",
                        classical_history.group(0),
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

            replacement = (
                ""
                if patch.patch_type in {"delete", "compact"}
                else patch.patch_text
            )
            text = text[: resolved.start] + replacement + text[resolved.end :]
            if (
                patch.patch_type != "compact"
                and any(span and span not in text for span in patch.preserve)
            ):
                violations.append(
                    RepairPatchViolation(
                        code="REPAIR_REGRESSION",
                        message="Patch 删除了自身声明必须保留的正文",
                        patch_index=index,
                    )
                )
                continue
            applied_count += 1

        final_chars = _nonspace_chars(text)
        if (
            server_template_mode
            and final_chars < plan.length_adjustment.min_chars
        ):
            violations.append(
                RepairPatchViolation(
                    code="PATCH_FINAL_TOO_SHORT",
                    message="应用全部局部 Patch 后正文仍低于服务端最小长度",
                    evidence=str(final_chars),
                )
            )
        if final_chars > plan.length_adjustment.max_chars:
            violations.append(
                RepairPatchViolation(
                    code="PATCH_FINAL_TOO_LONG",
                    message="应用局部 Patch 后正文超过服务端最大长度",
                    evidence=str(final_chars),
                )
            )
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
            applied_patches=patch_set,
            enforced_removals=enforced_removals,
        )


__all__ = [
    "PatchType",
    "ProviderRepairPatch",
    "ProviderRepairPatchSet",
    "RepairPatch",
    "RepairPatchAnchor",
    "RepairPatchApplyResult",
    "RepairPatchSet",
    "RepairPatchValidationReport",
    "RepairPatchValidator",
    "RepairPatchViolation",
]
