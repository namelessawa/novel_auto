"""Offline-only typed StateGuard decision candidate.

This module is a Phase 9 calibration consumer.  Production Narrator and
NarrativeStateGuard code must not import it.  An abstention means "retain the
baseline decision" in comparative reports; it is never an implicit acceptance.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from narrative.state_guard_trace import StateGuardDecisionTrace
from narrative.typed_continuity import TypedContinuityState


TYPED_CANDIDATE_SCHEMA_VERSION = "state-guard-typed-candidate-v1"


class CandidateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    requirement: str = ""
    status: Literal["pass", "conflict", "unknown"]
    evidence: list[str] = Field(default_factory=list)


class TypedCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["state-guard-typed-candidate-v1"] = (
        TYPED_CANDIDATE_SCHEMA_VERSION
    )
    decision: Literal["accept", "reject", "abstain"]
    hard_conflicts: list[str] = Field(default_factory=list)
    endpoint_checks: list[CandidateCheck] = Field(default_factory=list)
    ledger_checks: list[CandidateCheck] = Field(default_factory=list)
    evidence_checks: list[CandidateCheck] = Field(default_factory=list)
    used_typed_state: bool = False
    used_canonical_facts: bool = False
    abstain_reason: str = ""


def _abstain(reason: str) -> TypedCandidateDecision:
    return TypedCandidateDecision(
        decision="abstain",
        abstain_reason=reason,
        used_typed_state=False,
        used_canonical_facts=False,
    )


def _name_map(
    trace: StateGuardDecisionTrace,
    state: TypedContinuityState,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for character_id in state.characters:
        mapping[character_id.casefold()] = character_id
        display = trace.entity_names.get(character_id)
        if display:
            mapping[display.casefold()] = character_id
    return mapping


def _mentioned_characters(requirement: str, mapping: dict[str, str]) -> list[str]:
    folded = requirement.casefold()
    result: list[str] = []
    for name, character_id in mapping.items():
        if name in folded and character_id not in result:
            result.append(character_id)
    return result


def _prose_location_evidence(prose: str) -> tuple[str, list[str]]:
    negative_patterns = (
        "没有越过",
        "没有进入",
        "未进入",
        "仍停在外",
        "停在外侧",
        "内城门仍紧闭",
        "没有越过内门",
    )
    found_negative = [pattern for pattern in negative_patterns if pattern in prose]
    if found_negative:
        return "conflict", found_negative
    positive_patterns = (
        "进入城内",
        "进入门内",
        "跌进门内",
        "跨过内门",
        "越过内门",
        "滚过门线",
        "跨过出口",
        "穿过内门",
        "城门内侧",
        "仍在门内",
        "门线留在",
        "门内",
    )
    found_positive = [pattern for pattern in positive_patterns if pattern in prose]
    if found_positive:
        return "pass", found_positive
    return "unknown", []


def _structured_verifier_checks(
    trace: StateGuardDecisionTrace,
) -> tuple[list[CandidateCheck], list[str], bool]:
    checks: list[CandidateCheck] = []
    conflicts: list[str] = []
    if not trace.verifier_rounds:
        return checks, conflicts, False
    first = trace.verifier_rounds[0].get("normalised_output") or {}
    event_checks = first.get("event_checks") or []
    for event_check in event_checks:
        met = event_check.get("met")
        requirement = str(event_check.get("requirement") or "")
        evidence = [
            *[str(item) for item in event_check.get("prose_evidence") or []],
            *[str(item) for item in event_check.get("ledger_evidence_paths") or []],
        ]
        status: Literal["pass", "conflict", "unknown"]
        if met is True:
            status = "pass"
        elif met is False:
            status = "conflict"
            conflicts.append(f"structured verifier reports unmet endpoint: {requirement}")
        else:
            status = "unknown"
        checks.append(
            CandidateCheck(
                kind="verifier_event_check",
                requirement=requirement,
                status=status,
                evidence=evidence,
            )
        )
    for field in (
        "entity_grounding_conflicts",
        "prior_state_conflicts",
        "internal_conflicts",
        "ledger_conflicts",
    ):
        values = [str(value) for value in first.get(field) or []]
        if values:
            conflicts.extend(f"{field}: {value}" for value in values)
            checks.append(
                CandidateCheck(
                    kind=field,
                    status="conflict",
                    evidence=values,
                )
            )
    for round_payload in trace.verifier_rounds:
        normalised = round_payload.get("normalised_output") or {}
        fact_changes = [
            str(value) for value in normalised.get("fact_changes_from_original") or []
        ]
        if fact_changes:
            conflicts.extend(
                f"repair fact change: {value}" for value in fact_changes
            )
            checks.append(
                CandidateCheck(
                    kind="repair_fact_change",
                    status="conflict",
                    evidence=fact_changes,
                )
            )
    return checks, conflicts, True


def evaluate_typed_candidate(trace_payload: dict[str, Any]) -> TypedCandidateDecision:
    """Evaluate one complete trace without consulting fixture labels or final decision."""

    try:
        trace = StateGuardDecisionTrace.model_validate(trace_payload)
    except ValidationError as exc:
        return _abstain(f"invalid or incomplete Guard trace: {exc.errors()[0]['type']}")
    if trace.payload_completeness.missing_fields:
        return _abstain(
            "payload loss: " + ", ".join(trace.payload_completeness.missing_fields)
        )
    if not trace.original_draft.strip():
        return _abstain("prose is missing")
    if trace.repair_attempted and (
        not trace.repair_rounds
        or any(
            not str((round_payload.get("raw_output") or {}).get("narrative_text") or "").strip()
            for round_payload in trace.repair_rounds
        )
    ):
        return _abstain("repair prose is missing")
    if not trace.previous_typed_state:
        return _abstain("authoritative previous typed state is missing")
    if not trace.original_declared_typed_state:
        return _abstain("declared ledger cannot be typed")
    try:
        previous = TypedContinuityState.model_validate(trace.previous_typed_state)
        declared = TypedContinuityState.model_validate(
            trace.original_declared_typed_state
        )
    except ValidationError:
        return _abstain("previous or declared ledger cannot be typed")
    if not previous.time_marker.strip():
        return _abstain("previous typed state source is unclear")
    if not trace.required_end_states:
        return _abstain("required end state is missing")

    hard_conflicts: list[str] = []
    endpoint_checks: list[CandidateCheck] = []
    ledger_checks: list[CandidateCheck] = []
    evidence_checks: list[CandidateCheck] = []
    character_names = _name_map(trace, declared)
    location_ids = {
        str(item.get("location_id"))
        for item in trace.location_context
        if item.get("location_id")
    }
    parsed_requirement_count = 0
    prose = trace.original_draft

    for required in trace.required_end_states:
        requirement = str(required.get("requirement") or "").strip()
        if not requirement:
            return _abstain("required end state is ambiguous")
        requirement_parsed = False

        target_locations = [
            location_id
            for location_id in sorted(location_ids)
            if location_id.casefold() in requirement.casefold()
        ]
        has_location_semantics = bool(
            re.search(r"进入|仍在|到达|位于|越过|门内", requirement)
        )
        if has_location_semantics and not target_locations:
            return _abstain("location ontology is incomplete for a required endpoint")
        for target_location in target_locations:
            requirement_parsed = True
            subjects = _mentioned_characters(requirement, character_names)
            if "两人" in requirement or "他们" in requirement:
                if len(declared.characters) != 2:
                    return _abstain("multi-character movement relation is ambiguous")
                subjects = list(declared.characters)
            if not subjects:
                return _abstain("required location endpoint has no resolvable subject")
            for character_id in subjects:
                character = declared.characters.get(character_id)
                if character is None:
                    return _abstain("required character is absent from declared ledger")
                passed = character.location_id == target_location
                check = CandidateCheck(
                    kind="typed_location_endpoint",
                    requirement=requirement,
                    status="pass" if passed else "conflict",
                    evidence=[
                        f"characters.{character_id}.location_id={character.location_id!r}",
                        f"required={target_location!r}",
                    ],
                )
                endpoint_checks.append(check)
                if not passed:
                    hard_conflicts.append(
                        f"{character_id} ends at {character.location_id!r}, not {target_location!r}"
                    )
            prose_status, prose_evidence = _prose_location_evidence(prose)
            evidence_checks.append(
                CandidateCheck(
                    kind="prose_location_evidence",
                    requirement=requirement,
                    status=prose_status,
                    evidence=prose_evidence,
                )
            )
            if prose_status == "conflict":
                hard_conflicts.append(
                    f"prose explicitly contradicts location endpoint: {requirement}"
                )

        for item_id, item in declared.items.items():
            if item_id.casefold() not in requirement.casefold():
                continue
            if "持有" in requirement:
                requirement_parsed = True
                expected_holders = _mentioned_characters(requirement, character_names)
                if not expected_holders:
                    return _abstain("item holder endpoint has no resolvable character")
                passed = all(
                    holder in item.holder_character_ids for holder in expected_holders
                )
                ledger_checks.append(
                    CandidateCheck(
                        kind="typed_item_holder",
                        requirement=requirement,
                        status="pass" if passed else "conflict",
                        evidence=[
                            f"items.{item_id}.holder_character_ids={item.holder_character_ids!r}",
                            f"required_holders={expected_holders!r}",
                        ],
                    )
                )
                if not passed:
                    hard_conflicts.append(
                        f"{item_id} holder {item.holder_character_ids!r} does not include {expected_holders!r}"
                    )
            for condition in (
                "intact",
                "damaged",
                "destroyed",
                "consumed",
                "partial",
            ):
                if re.search(rf"(?:仍)?为{re.escape(condition)}", requirement):
                    requirement_parsed = True
                    passed = item.condition == condition
                    ledger_checks.append(
                        CandidateCheck(
                            kind="typed_item_condition",
                            requirement=requirement,
                            status="pass" if passed else "conflict",
                            evidence=[
                                f"items.{item_id}.condition={item.condition!r}",
                                f"required={condition!r}",
                            ],
                        )
                    )
                    if not passed:
                        hard_conflicts.append(
                            f"{item_id} condition {item.condition!r} is not {condition!r}"
                        )
            quantity_match = re.search(r"quantity\s*为\s*(\d+(?:\.\d+)?)", requirement)
            if quantity_match:
                requirement_parsed = True
                expected_quantity = float(quantity_match.group(1))
                actual_quantity = None if item.quantity is None else float(item.quantity)
                passed = actual_quantity == expected_quantity
                ledger_checks.append(
                    CandidateCheck(
                        kind="typed_item_quantity",
                        requirement=requirement,
                        status="pass" if passed else "conflict",
                        evidence=[
                            f"items.{item_id}.quantity={item.quantity!r}",
                            f"required={expected_quantity!r}",
                        ],
                    )
                )
                if not passed:
                    hard_conflicts.append(
                        f"{item_id} quantity {item.quantity!r} is not {expected_quantity!r}"
                    )

        if "伤势仍active" in requirement:
            requirement_parsed = True
            subjects = _mentioned_characters(requirement, character_names)
            if not subjects:
                return _abstain("injury endpoint has no resolvable character")
            for character_id in subjects:
                injuries = declared.characters[character_id].injuries
                passed = any(injury.status == "active" for injury in injuries)
                ledger_checks.append(
                    CandidateCheck(
                        kind="typed_active_injury",
                        requirement=requirement,
                        status="pass" if passed else "conflict",
                        evidence=[
                            f"characters.{character_id}.injuries="
                            f"{[injury.model_dump(mode='json') for injury in injuries]!r}"
                        ],
                    )
                )
                if not passed:
                    hard_conflicts.append(f"{character_id} has no active injury")

        if "代价" in requirement:
            requirement_parsed = True
            explicit_absence = bool(re.search(r"没有[^。；]*代价|未[^。；]*代价", prose))
            status: Literal["pass", "conflict", "unknown"] = (
                "conflict" if explicit_absence else "unknown"
            )
            evidence_checks.append(
                CandidateCheck(
                    kind="prose_required_cost",
                    requirement=requirement,
                    status=status,
                    evidence=["prose explicitly says no cost"] if explicit_absence else [],
                )
            )
            if explicit_absence:
                hard_conflicts.append("required narrative cost is explicitly absent")

        if "不得新增无来源" in requirement:
            requirement_parsed = True
            explicit_leak = "无来源" in prose or "此前没有人" in prose
            evidence_checks.append(
                CandidateCheck(
                    kind="knowledge_source_boundary",
                    requirement=requirement,
                    status="conflict" if explicit_leak else "unknown",
                    evidence=["prose marks knowledge as ungrounded"] if explicit_leak else [],
                )
            )
            if explicit_leak:
                hard_conflicts.append("prose explicitly introduces ungrounded knowledge")

        if ("出口已锁死" in requirement or "出口封死" in requirement):
            requirement_parsed = True
            evidence = [
                marker
                for marker in ("锁死", "落栓", "封住", "封死")
                if marker in prose
            ]
            evidence_checks.append(
                CandidateCheck(
                    kind="prose_exit_closed",
                    requirement=requirement,
                    status="pass" if evidence else "unknown",
                    evidence=evidence,
                )
            )

        if not requirement_parsed:
            return _abstain("required end state cannot be typed or grounded unambiguously")
        parsed_requirement_count += 1

    verifier_checks, verifier_conflicts, verifier_available = (
        _structured_verifier_checks(trace)
    )
    evidence_checks.extend(verifier_checks)
    hard_conflicts.extend(verifier_conflicts)
    if not verifier_available:
        return _abstain("structured verifier evidence is missing")
    if parsed_requirement_count != len(trace.required_end_states):
        return _abstain("not all required end states were parsed")

    return TypedCandidateDecision(
        decision="reject" if hard_conflicts else "accept",
        hard_conflicts=list(dict.fromkeys(hard_conflicts)),
        endpoint_checks=endpoint_checks,
        ledger_checks=ledger_checks,
        evidence_checks=evidence_checks,
        used_typed_state=True,
        used_canonical_facts=False,
        abstain_reason="",
    )


__all__ = [
    "TYPED_CANDIDATE_SCHEMA_VERSION",
    "CandidateCheck",
    "TypedCandidateDecision",
    "evaluate_typed_candidate",
]
