"""Unified deterministic validator for author and simulation candidates."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from story.models import (
    CanonicalState,
    SectionGoal,
    StateDeltaOperation,
    StoryBible,
    StoryThread,
    StoryThreadRepository,
    ThreadChange,
    ValidationReport,
    ValidationViolation,
    WriterCandidate,
    utc_now,
)


ALLOWED_DELTA_ROOTS = {
    "world_time",
    "world",
    "characters",
    "items",
    "relationships",
    "character_knowledge",
    "reader_knowledge",
    "active_threads",
    "plot_position",
    "last_scene_state",
    "canonical_facts",
}

BLOCKING_DELTA_CODES = {
    "STORY_BIBLE_IMMUTABLE",
    "DELTA_EVIDENCE_MISSING",
    "DELTA_NARRATIVE_MISMATCH",
    "DELTA_PATH_FORBIDDEN",
    "DELTA_PATH_INVALID",
    "DELTA_TYPE_INCOMPATIBLE",
    "CHARACTER_UNKNOWN",
    "DEAD_CHARACTER_REVIVAL",
    "LOCATION_UNKNOWN",
    "LOCATION_JUMP",
    "ITEM_UNKNOWN",
    "ITEM_OWNER_CONFLICT",
    "ITEM_TARGET_UNKNOWN",
    "ITEM_TRANSFER_UNNARRATED",
    "KNOWLEDGE_CHARACTER_UNKNOWN",
}


def _segments(path: str) -> list[str]:
    return [part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]]


def _contains_evidence(narrative: str, evidence: str) -> bool:
    evidence = evidence.strip()
    if not evidence:
        return False
    if evidence in narrative:
        return True
    words = [item for item in re.split(r"[，。！？；：、,.;:\s]+", evidence) if len(item) >= 2]
    return bool(words) and sum(word in narrative for word in words) >= min(2, len(words))


def _theme_terms(bible: StoryBible, goal: SectionGoal) -> set[str]:
    source = " ".join(
        [bible.theme, bible.central_question, goal.objective, *bible.main_conflicts]
    )
    chunks = re.split(r"[，。！？；：、,/|\s与和的]+", source)
    terms = {chunk for chunk in chunks if 2 <= len(chunk) <= 12}
    for chunk in list(terms):
        if len(chunk) >= 4:
            terms.update(chunk[i : i + 2] for i in range(len(chunk) - 1))
    return terms


def _world_location_ids(state: CanonicalState) -> set[str]:
    out: set[str] = set()
    locations = state.world.get("locations", [])
    if isinstance(locations, dict):
        out.update(map(str, locations))
    elif isinstance(locations, list):
        for item in locations:
            if isinstance(item, dict):
                out.add(str(item.get("id") or item.get("name") or ""))
            elif item:
                out.add(str(item))
    out.discard("")
    return out


def _max_severity(violations: list[ValidationViolation]) -> str:
    rank = {"low": 0, "medium": 1, "high": 2}
    return max((item.severity for item in violations), key=rank.get, default="low")


class StoryValidator:
    """Validates candidate prose and deltas without writing persistent state."""

    def validate(
        self,
        *,
        bible: StoryBible,
        state: CanonicalState,
        threads: StoryThreadRepository,
        goal: SectionGoal,
        candidate: WriterCandidate,
        source_mode: str = "author",
    ) -> ValidationReport:
        violations: list[ValidationViolation] = []
        narrative = candidate.narrative_text
        locations = _world_location_ids(state)
        validated_delta: list[StateDeltaOperation] = []
        preview = state.model_dump(mode="python")

        for operation in candidate.state_delta:
            start = len(violations)
            parts = _segments(operation.path)
            root = parts[0] if parts else ""
            if root in {"story_bible", "theme", "immutable_world_rules"}:
                violations.append(
                    self._violation(
                        "STORY_BIBLE_IMMUTABLE",
                        "StateDelta 不得修改 StoryBible、主题或不可变规则",
                        "high",
                        operation,
                    )
                )
                continue
            if root not in ALLOWED_DELTA_ROOTS:
                violations.append(
                    self._violation(
                        "DELTA_PATH_FORBIDDEN",
                        f"不允许的状态路径: {operation.path}",
                        "high",
                        operation,
                    )
                )
                continue
            self._validate_operation(
                operation,
                parts=parts,
                narrative=narrative,
                state=state,
                locations=locations,
                violations=violations,
                trusted_projection=(source_mode == "simulation"),
            )
            new_codes = {item.code for item in violations[start:]}
            if new_codes & BLOCKING_DELTA_CODES:
                continue
            try:
                self._apply_one(preview, parts, operation)
            except (TypeError, ValueError) as exc:
                violations.append(
                    self._violation(
                        "DELTA_TYPE_INCOMPATIBLE",
                        f"状态操作与目标字段不兼容: {exc}",
                        "high",
                        operation,
                    )
                )
                continue
            validated_delta.append(operation)

        thread_changes = self._validate_threads(
            candidate, threads, bible, narrative, violations
        )
        self._validate_bible(bible, goal, narrative, candidate, violations)
        self._validate_reader_boundary(state, narrative, violations)
        severity = _max_severity(violations)
        accepted = not any(item.severity == "high" for item in violations)
        return ValidationReport(
            accepted=accepted,
            severity=severity,
            violations=violations,
            repairable=True,
            validated_delta=validated_delta,
            thread_changes=thread_changes,
        )

    def apply_delta(
        self,
        state: CanonicalState,
        operations: list[StateDeltaOperation],
    ) -> CanonicalState:
        payload = state.model_dump(mode="python")
        for operation in operations:
            parts = _segments(operation.path)
            if not parts or parts[0] not in ALLOWED_DELTA_ROOTS:
                raise ValueError(f"unvalidated delta path: {operation.path}")
            self._apply_one(payload, parts, operation)
        payload["revision"] = state.revision + 1
        payload["updated_at"] = utc_now()
        return CanonicalState.model_validate(payload)

    def apply_thread_changes(
        self,
        repository: StoryThreadRepository,
        changes: list[ThreadChange],
        *,
        target_revision: int,
    ) -> StoryThreadRepository:
        updated = copy.deepcopy(repository.model_dump(mode="python"))
        threads = updated["threads"]
        for change in changes:
            if change.action == "opened":
                thread = change.thread.model_copy(
                    update={
                        "status": "open",
                        "opened_at_revision": target_revision,
                        "updated_at_revision": target_revision,
                    }
                )
            else:
                existing = StoryThread.model_validate(threads[change.thread.id])
                evidence = list(
                    dict.fromkeys(existing.evidence + change.thread.evidence)
                )
                involved = list(
                    dict.fromkeys(
                        existing.involved_characters
                        + change.thread.involved_characters
                    )
                )
                updates: dict[str, Any] = {
                    "status": "advancing" if change.action == "advanced" else "resolved",
                    "evidence": evidence,
                    "involved_characters": involved,
                    "updated_at_revision": target_revision,
                }
                if "urgency" in change.thread.model_fields_set:
                    updates["urgency"] = change.thread.urgency
                if change.action == "resolved":
                    updates["resolution_evidence"] = list(
                        dict.fromkeys(
                            existing.resolution_evidence
                            + change.thread.resolution_evidence
                        )
                    )
                thread = existing.model_copy(update=updates)
            threads[thread.id] = thread.model_dump(mode="python")
        updated["revision"] = repository.revision + 1
        updated["updated_at"] = utc_now()
        return StoryThreadRepository.model_validate(updated)

    def _validate_operation(
        self,
        operation: StateDeltaOperation,
        *,
        parts: list[str],
        narrative: str,
        state: CanonicalState,
        locations: set[str],
        violations: list[ValidationViolation],
        trusted_projection: bool = False,
    ) -> None:
        if not operation.evidence.strip():
            violations.append(
                self._violation(
                    "DELTA_EVIDENCE_MISSING",
                    "状态变化缺少正文证据",
                    "medium",
                    operation,
                    repair_hint="为该变化补充最小、明确的正文依据",
                )
            )
        elif not _contains_evidence(narrative, operation.evidence):
            violations.append(
                self._violation(
                    "DELTA_NARRATIVE_MISMATCH",
                    "StateDelta 声称的证据未出现在正文中",
                    "high",
                    operation,
                    repair_hint="删除无依据变化或在正文中写明变化过程",
                )
            )

        if not self._path_shape_is_valid(parts, operation):
            violations.append(
                self._violation(
                    "DELTA_PATH_INVALID",
                    f"状态路径层级或操作类型无效: {operation.path}",
                    "high",
                    operation,
                )
            )
            return

        if parts[0] == "characters" and len(parts) >= 2:
            character_id = parts[1]
            if character_id not in state.characters:
                violations.append(
                    self._violation(
                        "CHARACTER_UNKNOWN",
                        f"角色 {character_id} 不存在于 CanonicalState",
                        "high",
                        operation,
                    )
                )
                return
            field = parts[2] if len(parts) >= 3 else ""
            current = state.characters[character_id]
            if field in {"alive", "is_alive"} and operation.op == "set":
                was_alive = bool(current.get(field, current.get("alive", True)))
                if not was_alive and bool(operation.value):
                    violations.append(
                        self._violation(
                            "DEAD_CHARACTER_REVIVAL",
                            f"已死亡角色 {character_id} 不能无证据复活",
                            "high",
                            operation,
                            repair_hint="保持角色死亡，或提供符合世界规则的明确机制",
                        )
                    )
            if field in {"location", "current_location"} and operation.op == "set":
                destination = str(operation.value or "")
                if locations and destination not in locations:
                    violations.append(
                        self._violation(
                            "LOCATION_UNKNOWN",
                            f"地点 {destination} 不存在于 CanonicalState.world",
                            "high",
                            operation,
                        )
                    )
                previous = str(current.get(field, current.get("current_location", "")) or "")
                movement_words = ("前往", "抵达", "离开", "赶到", "走进", "来到", "移动")
                if previous and previous != destination and not trusted_projection and not any(
                    word in narrative for word in movement_words
                ):
                    violations.append(
                        self._violation(
                            "LOCATION_JUMP",
                            f"角色 {character_id} 从 {previous} 到 {destination} 缺少移动过程",
                            "high",
                            operation,
                            repair_hint="补写最小移动过渡",
                        )
                    )

        if parts[0] == "character_knowledge" and len(parts) >= 2:
            character_id = parts[1]
            if character_id not in state.characters:
                violations.append(
                    self._violation(
                        "KNOWLEDGE_CHARACTER_UNKNOWN",
                        f"知识边界引用未知角色 {character_id}",
                        "high",
                        operation,
                    )
                )

        if parts[0] == "items" and len(parts) >= 2:
            item_id = parts[1]
            creates_item = (
                item_id not in state.items
                and operation.op == "set"
                and len(parts) == 2
                and isinstance(operation.value, dict)
            )
            if item_id not in state.items and not creates_item:
                violations.append(
                    self._violation(
                        "ITEM_UNKNOWN",
                        f"物品 {item_id} 不存在",
                        "high",
                        operation,
                    )
                )
            if operation.op == "transfer":
                self._validate_transfer(operation, item_id, narrative, state, violations)

    def _validate_transfer(
        self,
        operation: StateDeltaOperation,
        item_id: str,
        narrative: str,
        state: CanonicalState,
        violations: list[ValidationViolation],
    ) -> None:
        value = operation.value if isinstance(operation.value, dict) else {}
        source = str(value.get("from") or "")
        target = str(value.get("to") or "")
        owners = list(map(str, state.items.get(item_id, {}).get("owners", [])))
        if source not in owners:
            violations.append(
                self._violation(
                    "ITEM_OWNER_CONFLICT",
                    f"{source or '未知来源'} 并不持有物品 {item_id}",
                    "high",
                    operation,
                )
            )
        if target not in state.characters:
            violations.append(
                self._violation(
                    "ITEM_TARGET_UNKNOWN",
                    f"物品接收者 {target} 不存在",
                    "high",
                    operation,
                )
            )
        target_name = str(state.characters.get(target, {}).get("name") or "")
        target_is_narrated = bool(
            target and (target in narrative or (target_name and target_name in narrative))
        )
        if item_id not in narrative or not target_is_narrated:
            violations.append(
                self._violation(
                    "ITEM_TRANSFER_UNNARRATED",
                    f"物品 {item_id} 的转交未在正文中明确出现",
                    "high",
                    operation,
                )
            )

    def _validate_threads(
        self,
        candidate: WriterCandidate,
        current: StoryThreadRepository,
        bible: StoryBible,
        narrative: str,
        violations: list[ValidationViolation],
    ) -> list[ThreadChange]:
        valid: list[ThreadChange] = []
        opened_ids: set[str] = set()
        for thread in candidate.threads_opened:
            start = len(violations)
            existing = current.threads.get(thread.id)
            if thread.id in opened_ids or (existing and existing.status not in {"resolved", "abandoned"}):
                violations.append(
                    ValidationViolation(
                        code="THREAD_DUPLICATE_OPEN",
                        message=f"活动故事线 {thread.id} 不能重复开启",
                        severity="high",
                        path=f"/threads/{thread.id}",
                    )
                )
            elif existing:
                violations.append(
                    ValidationViolation(
                        code="THREAD_ALREADY_CLOSED",
                        message=f"已关闭故事线 {thread.id} 不能重开",
                        severity="high",
                        path=f"/threads/{thread.id}",
                    )
                )
                if existing.status == "resolved":
                    violations.append(
                        ValidationViolation(
                            code="RESOLVED_THREAD_REOPENED",
                            message=f"已解决故事线 {thread.id} 不能作为新谜团重开",
                            severity="high",
                            path=f"/threads/{thread.id}",
                        )
                    )
            self._validate_main_conflict_abandon(thread, bible, violations)
            opened_ids.add(thread.id)
            if len(violations) == start:
                valid.append(ThreadChange(action="opened", thread=thread))

        for thread in candidate.threads_advanced:
            start = len(violations)
            existing = current.threads.get(thread.id)
            if existing is None:
                violations.append(
                    ValidationViolation(
                        code="THREAD_ADVANCE_UNKNOWN",
                        message=f"不能推进不存在的故事线 {thread.id}",
                        severity="high",
                        path=f"/threads/{thread.id}",
                    )
                )
            elif existing.status in {"resolved", "abandoned"}:
                violations.append(
                    ValidationViolation(
                        code="THREAD_ALREADY_CLOSED",
                        message=f"已关闭故事线 {thread.id} 不能继续推进",
                        severity="high",
                        path=f"/threads/{thread.id}",
                    )
                )
            else:
                self._validate_thread_immutable_fields(thread, existing, violations)
            evidence = [item.strip() for item in thread.evidence if item.strip()]
            if not evidence or not any(_contains_evidence(narrative, item) for item in evidence):
                violations.append(
                    ValidationViolation(
                        code="THREAD_ADVANCE_NO_EVIDENCE",
                        message=f"故事线 {thread.id} 缺少可定位的推进证据",
                        severity="high",
                        path=f"/threads/{thread.id}",
                    )
                )
            self._validate_main_conflict_abandon(thread, bible, violations)
            if len(violations) == start:
                valid.append(ThreadChange(action="advanced", thread=thread))

        for thread in candidate.threads_resolved:
            start = len(violations)
            existing = current.threads.get(thread.id)
            if existing is None:
                violations.append(
                    ValidationViolation(
                        code="THREAD_UNKNOWN",
                        message=f"不能解决不存在的故事线 {thread.id}",
                        severity="high",
                        path=f"/threads/{thread.id}",
                    )
                )
                continue
            if existing.status in {"resolved", "abandoned"}:
                violations.append(
                    ValidationViolation(
                        code="THREAD_ALREADY_CLOSED",
                        message=f"故事线 {thread.id} 已经关闭",
                        severity="high",
                        path=f"/threads/{thread.id}",
                    )
                )
            self._validate_thread_immutable_fields(thread, existing, violations)
            evidence = [item.strip() for item in thread.resolution_evidence if item.strip()]
            if not evidence or not any(_contains_evidence(narrative, item) for item in evidence):
                violations.append(
                    ValidationViolation(
                        code="THREAD_RESOLUTION_NO_EVIDENCE",
                        message=f"故事线 {thread.id} 没有正文兑现证据，不能关闭",
                        severity="high",
                        path=f"/threads/{thread.id}",
                        repair_hint="保留为 advancing，或补充明确兑现证据",
                    )
                )
            unmet = [
                requirement
                for requirement in existing.resolution_requirements
                if not _contains_evidence(narrative, requirement)
            ]
            if unmet:
                violations.append(
                    ValidationViolation(
                        code="THREAD_REQUIREMENTS_UNMET",
                        message=f"故事线 {thread.id} 尚未满足兑现要求: {'；'.join(unmet)}",
                        severity="high",
                        path=f"/threads/{thread.id}",
                    )
                )
            self._validate_main_conflict_abandon(thread, bible, violations)
            if len(violations) == start:
                valid.append(ThreadChange(action="resolved", thread=thread))
        return valid

    @staticmethod
    def _path_shape_is_valid(
        parts: list[str], operation: StateDeltaOperation
    ) -> bool:
        if not parts:
            return False
        root = parts[0]
        if operation.op == "transfer":
            return root == "items" and len(parts) in {2, 3}
        minimum = {
            "world_time": 1,
            "world": 2,
            "characters": 3,
            "items": 2,
            "relationships": 2,
            "character_knowledge": 2,
            "reader_knowledge": 2,
            "active_threads": 2,
            "plot_position": 2,
            "last_scene_state": 2,
            "canonical_facts": 2,
        }.get(root)
        if minimum is None or len(parts) < minimum:
            return False
        if root == "world_time":
            return len(parts) == 1 and operation.op in {"set", "add"}
        return True

    @staticmethod
    def _validate_thread_immutable_fields(
        proposed: StoryThread,
        existing: StoryThread,
        violations: list[ValidationViolation],
    ) -> None:
        for field in ("type", "description", "origin_refs", "opened_at_revision", "source"):
            if field not in proposed.model_fields_set:
                continue
            if getattr(proposed, field) == getattr(existing, field):
                continue
            violations.append(
                ValidationViolation(
                    code="THREAD_FIELD_OVERRIDE_FORBIDDEN",
                    message=f"故事线 {proposed.id} 的来源字段 {field} 不可由 Writer 覆盖",
                    severity="high",
                    path=f"/threads/{proposed.id}",
                )
            )

    @staticmethod
    def _validate_main_conflict_abandon(
        thread: StoryThread,
        bible: StoryBible,
        violations: list[ValidationViolation],
    ) -> None:
        if thread.status != "abandoned":
            return
        description = thread.description.strip()
        matches = any(
            description == conflict.strip()
            or (description and description in conflict)
            or (conflict and conflict in description)
            for conflict in bible.main_conflicts
        )
        if matches:
            violations.append(
                ValidationViolation(
                    code="THREAD_MAIN_CONFLICT_ABANDON_FORBIDDEN",
                    message=f"StoryBible 主冲突对应故事线 {thread.id} 不能由普通输出放弃",
                    severity="high",
                    path=f"/threads/{thread.id}",
                )
            )

    def _validate_bible(
        self,
        bible: StoryBible,
        goal: SectionGoal,
        narrative: str,
        candidate: WriterCandidate,
        violations: list[ValidationViolation],
    ) -> None:
        combined_rules = bible.immutable_world_rules + bible.forbidden_deviations
        forbids_revival = any(
            any(marker in rule for marker in ("禁止复活", "不能复活", "死亡不可逆", "死者不可复生"))
            for rule in combined_rules
        )
        if forbids_revival and any(marker in narrative for marker in ("复活", "死而复生", "重新活了")):
            violations.append(
                ValidationViolation(
                    code="IMMUTABLE_RULE_REVIVAL",
                    message="正文触犯了 StoryBible 的死亡不可逆规则",
                    severity="high",
                    path="/story_bible/immutable_world_rules",
                    repair_hint="移除复活事实，保留死亡的既定后果",
                )
            )

        for deviation in bible.forbidden_deviations:
            if len(deviation) >= 2 and deviation in narrative:
                violations.append(
                    ValidationViolation(
                        code="FORBIDDEN_DEVIATION",
                        message=f"正文直接触犯禁止偏移：{deviation}",
                        severity="high",
                        path="/story_bible/forbidden_deviations",
                    )
                )

        if len(narrative) >= 200:
            terms = _theme_terms(bible, goal)
            hits = sorted(term for term in terms if term in narrative or term in candidate.section_summary)
            if terms and not hits:
                violations.append(
                    ValidationViolation(
                        code="THEME_WEAK_SIGNAL",
                        message="本节未检测到主题、主冲突或章节目标的可追踪呼应",
                        severity="medium",
                        path="/story_bible/theme",
                        repair_hint="在不直说主题的前提下加入一次选择、代价或冲突呼应",
                    )
                )

    def _validate_reader_boundary(
        self,
        state: CanonicalState,
        narrative: str,
        violations: list[ValidationViolation],
    ) -> None:
        known = state.reader_knowledge.get("known_facts", [])
        reveal_markers = ("原来", "首次揭示", "终于揭晓", "第一次知道")
        if not any(marker in narrative for marker in reveal_markers):
            return
        for raw in known:
            fact = str(raw.get("fact") if isinstance(raw, dict) else raw).strip()
            if fact and fact in narrative:
                violations.append(
                    ValidationViolation(
                        code="READER_KNOWLEDGE_REVEALED_AGAIN",
                        message="读者已知事实被重新包装为首次揭示",
                        severity="medium",
                        path="/reader_knowledge",
                        evidence=fact[:160],
                    )
                )
                break

    @staticmethod
    def _thread_changes(candidate: WriterCandidate) -> list[ThreadChange]:
        return [
            *[ThreadChange(action="opened", thread=item) for item in candidate.threads_opened],
            *[ThreadChange(action="advanced", thread=item) for item in candidate.threads_advanced],
            *[ThreadChange(action="resolved", thread=item) for item in candidate.threads_resolved],
        ]

    @staticmethod
    def _violation(
        code: str,
        message: str,
        severity: str,
        operation: StateDeltaOperation,
        *,
        repair_hint: str = "",
    ) -> ValidationViolation:
        return ValidationViolation(
            code=code,
            message=message,
            severity=severity,
            path=operation.path,
            evidence=operation.evidence[:240],
            repair_hint=repair_hint,
        )

    @staticmethod
    def _apply_one(
        payload: dict[str, Any],
        parts: list[str],
        operation: StateDeltaOperation,
    ) -> None:
        if operation.op == "transfer":
            if parts[0] != "items" or len(parts) < 2:
                raise ValueError("transfer is only valid for /items/{id}")
            item = payload["items"].setdefault(parts[1], {"id": parts[1], "owners": []})
            value = operation.value if isinstance(operation.value, dict) else {}
            source = str(value.get("from") or "")
            target = str(value.get("to") or "")
            owners = list(map(str, item.get("owners", [])))
            owners = [owner for owner in owners if owner != source]
            if target and target not in owners:
                owners.append(target)
            item["owners"] = owners
            return

        parent: Any = payload
        for part in parts[:-1]:
            if isinstance(parent, dict):
                parent = parent.setdefault(part, {})
            else:
                raise ValueError(f"delta path traverses non-object: /{'/'.join(parts)}")
        key = parts[-1]
        if not isinstance(parent, dict):
            raise ValueError(f"delta parent is not an object: /{'/'.join(parts)}")
        current = parent.get(key)
        if operation.op == "set":
            if key in parent and not StoryValidator._values_compatible(
                current, operation.value
            ):
                raise TypeError(
                    f"set cannot replace {type(current).__name__} with "
                    f"{type(operation.value).__name__}"
                )
            parent[key] = copy.deepcopy(operation.value)
        elif operation.op == "add":
            if not isinstance(current, (int, float)) or not isinstance(operation.value, (int, float)):
                raise ValueError("add requires numeric current and value")
            parent[key] = current + operation.value
        elif operation.op == "append":
            target = parent.setdefault(key, [])
            if not isinstance(target, list):
                raise ValueError("append requires a list target")
            values = operation.value if isinstance(operation.value, list) else [operation.value]
            for value in values:
                if value not in target:
                    target.append(copy.deepcopy(value))
        elif operation.op == "remove":
            if isinstance(current, list):
                values = operation.value if isinstance(operation.value, list) else [operation.value]
                parent[key] = [value for value in current if value not in values]
            elif key in parent:
                del parent[key]
        else:
            raise ValueError(f"unsupported operation: {operation.op}")

    @staticmethod
    def _values_compatible(current: Any, proposed: Any) -> bool:
        """Keep dynamically shaped CanonicalState fields type-stable."""

        if current is None:
            return True
        if isinstance(current, bool):
            return isinstance(proposed, bool)
        if isinstance(current, (int, float)):
            return isinstance(proposed, (int, float)) and not isinstance(proposed, bool)
        if isinstance(current, dict):
            return isinstance(proposed, dict)
        if isinstance(current, list):
            return isinstance(proposed, list)
        if isinstance(current, str):
            return isinstance(proposed, str)
        return isinstance(proposed, type(current))


def report_as_repair_prompt(report: ValidationReport, candidate: WriterCandidate) -> str:
    """Minimal repair input: original prose, violations, and preservation facts only."""

    violations = [
        {
            "code": item.code,
            "message": item.message,
            "evidence": item.evidence,
            "repair_hint": item.repair_hint,
        }
        for item in report.violations
        if item.severity in {"high", "medium"}
    ]
    return json.dumps(
        {
            "original_narrative": candidate.narrative_text,
            "violations": violations,
            **report.repair_context,
            "instruction": (
                "只修正明确违规的最小范围；不得新增事实；"
                "只返回包含修复后完整 narrative_text 的 JSON 补丁。"
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


__all__ = ["ALLOWED_DELTA_ROOTS", "StoryValidator", "report_as_repair_prompt"]
