"""Versioned, typed continuity ledger with loss-aware legacy normalization.

This module is intentionally consumer-neutral in Phase 8 Iteration 12.  It does
not alter TickState, Narrator, StateGuard or CanonicalFact projection.  Callers can
validate a strict typed payload or obtain a non-authoritative best-effort view of a
legacy payload while retaining the original JSON-safe data for audit.
"""

from __future__ import annotations

import json
import math
from typing import Annotated, Any, Collection, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)


StableId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
]
MovementStatus = Literal[
    "stationary", "departing", "in_transit", "arrived", "unknown"
]
AliveStatus = Literal["alive", "dead", "missing", "unknown"]
InjurySeverity = Literal["minor", "moderate", "severe", "critical", "unknown"]
InjuryStatus = Literal["active", "worsening", "treated", "healed", "unknown"]
ItemCondition = Literal[
    "intact", "damaged", "destroyed", "consumed", "partial", "unknown"
]


_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    str_strip_whitespace=True,
    validate_assignment=True,
)


class InjuryState(BaseModel):
    model_config = _MODEL_CONFIG

    injury_id: StableId
    body_part: StableId = "unknown"
    severity: InjurySeverity = "unknown"
    status: InjuryStatus = "unknown"
    source_event_id: StableId | None = None


class CharacterContinuity(BaseModel):
    model_config = _MODEL_CONFIG

    character_id: StableId
    location_id: StableId | None = None
    movement_status: MovementStatus = "unknown"
    destination_location_id: StableId | None = None
    alive_status: AliveStatus = "unknown"
    injuries: list[InjuryState] = Field(default_factory=list)
    supporting_character_ids: list[StableId] = Field(default_factory=list)
    carried_by_character_id: StableId | None = None
    knowledge_fact_ids: list[StableId] = Field(default_factory=list)

    @field_validator(
        "supporting_character_ids", "knowledge_fact_ids", mode="after"
    )
    @classmethod
    def _deduplicate_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def _validate_injury_ids(self) -> "CharacterContinuity":
        ids = [injury.injury_id for injury in self.injuries]
        if len(ids) != len(set(ids)):
            raise ValueError("injury_id must be unique within a character")
        return self


class ItemContinuity(BaseModel):
    model_config = _MODEL_CONFIG

    item_id: StableId
    holder_character_ids: list[StableId] = Field(default_factory=list)
    location_id: StableId | None = None
    quantity: int | float | None = None
    condition: ItemCondition = "unknown"
    container_item_id: StableId | None = None

    @field_validator("holder_character_ids", mode="after")
    @classmethod
    def _deduplicate_holders(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("quantity", mode="before")
    @classmethod
    def _validate_quantity(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("quantity must be a JSON number or null")
        if not math.isfinite(float(value)) or value < 0:
            raise ValueError("quantity must be finite and non-negative")
        return value


class TypedContinuityState(BaseModel):
    model_config = _MODEL_CONFIG

    schema_version: Literal["1"] = "1"
    time_marker: str = Field(default="", max_length=300)
    characters: dict[StableId, CharacterContinuity] = Field(default_factory=dict)
    items: dict[StableId, ItemContinuity] = Field(default_factory=dict)
    newly_known_fact_ids: dict[StableId, list[StableId]] = Field(
        default_factory=dict
    )
    active_open_loop_ids: list[StableId] = Field(default_factory=list)

    @field_validator("active_open_loop_ids", mode="after")
    @classmethod
    def _deduplicate_loop_ids(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("newly_known_fact_ids", mode="after")
    @classmethod
    def _deduplicate_new_knowledge(
        cls, values: dict[str, list[str]]
    ) -> dict[str, list[str]]:
        return {key: list(dict.fromkeys(items)) for key, items in values.items()}

    @model_validator(mode="after")
    def _keys_match_embedded_ids(self) -> "TypedContinuityState":
        for key, character in self.characters.items():
            if key != character.character_id:
                raise ValueError(
                    f"characters key {key!r} does not match character_id "
                    f"{character.character_id!r}"
                )
        for key, item in self.items.items():
            if key != item.item_id:
                raise ValueError(
                    f"items key {key!r} does not match item_id {item.item_id!r}"
                )
        return self


ContinuityIssueCode = Literal[
    "unknown_character_id",
    "unknown_location_id",
    "unknown_item_id",
    "unknown_fact_id",
    "unknown_open_loop_id",
    "unknown_event_id",
    "invalid_typed_payload",
    "unmapped_legacy_value",
]


class ContinuityIssue(BaseModel):
    model_config = _MODEL_CONFIG

    code: ContinuityIssueCode
    path: str
    value: Any = None


class ContinuityNormalizationResult(BaseModel):
    model_config = _MODEL_CONFIG

    source_schema: Literal["typed_v1", "legacy", "invalid"]
    typed_state: TypedContinuityState
    raw_payload: Any
    issues: list[ContinuityIssue] = Field(default_factory=list)
    authoritative_eligible: bool = False
    references_checked: bool = False


def _json_safe_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError):
        def sanitize(item: Any, depth: int = 0) -> Any:
            if depth >= 12:
                return str(item)
            if item is None or isinstance(item, (str, bool, int)):
                return item
            if isinstance(item, float):
                return item if math.isfinite(item) else str(item)
            if isinstance(item, dict):
                return {
                    str(key): sanitize(child, depth + 1)
                    for key, child in list(item.items())[:200]
                }
            if isinstance(item, (list, tuple)):
                return [sanitize(child, depth + 1) for child in item[:200]]
            return str(item)

        return sanitize(value)


def _id_or_none(
    value: Any,
    *,
    allowed: Collection[str] | None,
) -> str | None:
    try:
        parsed = TypeId(value=value).value
    except ValidationError:
        return None
    if allowed is not None and parsed not in allowed:
        return None
    return parsed


class TypeId(BaseModel):
    """Small Pydantic adapter used by the conservative legacy normalizer."""

    model_config = _MODEL_CONFIG
    value: StableId


def validate_continuity_references(
    state: TypedContinuityState,
    *,
    valid_character_ids: Collection[str] | None = None,
    valid_location_ids: Collection[str] | None = None,
    valid_item_ids: Collection[str] | None = None,
    valid_fact_ids: Collection[str] | None = None,
    valid_open_loop_ids: Collection[str] | None = None,
    valid_event_ids: Collection[str] | None = None,
) -> list[ContinuityIssue]:
    issues: list[ContinuityIssue] = []

    def check(
        value: str | None,
        allowed: Collection[str] | None,
        code: ContinuityIssueCode,
        path: str,
    ) -> None:
        if value is not None and allowed is not None and value not in allowed:
            issues.append(ContinuityIssue(code=code, path=path, value=value))

    for cid, character in state.characters.items():
        check(
            cid,
            valid_character_ids,
            "unknown_character_id",
            f"characters.{cid}.character_id",
        )
        check(
            character.location_id,
            valid_location_ids,
            "unknown_location_id",
            f"characters.{cid}.location_id",
        )
        check(
            character.destination_location_id,
            valid_location_ids,
            "unknown_location_id",
            f"characters.{cid}.destination_location_id",
        )
        check(
            character.carried_by_character_id,
            valid_character_ids,
            "unknown_character_id",
            f"characters.{cid}.carried_by_character_id",
        )
        for index, supporter_id in enumerate(character.supporting_character_ids):
            check(
                supporter_id,
                valid_character_ids,
                "unknown_character_id",
                f"characters.{cid}.supporting_character_ids.{index}",
            )
        for index, fact_id in enumerate(character.knowledge_fact_ids):
            check(
                fact_id,
                valid_fact_ids,
                "unknown_fact_id",
                f"characters.{cid}.knowledge_fact_ids.{index}",
            )
        for index, injury in enumerate(character.injuries):
            check(
                injury.source_event_id,
                valid_event_ids,
                "unknown_event_id",
                f"characters.{cid}.injuries.{index}.source_event_id",
            )

    for item_id, item in state.items.items():
        check(
            item_id,
            valid_item_ids,
            "unknown_item_id",
            f"items.{item_id}.item_id",
        )
        check(
            item.location_id,
            valid_location_ids,
            "unknown_location_id",
            f"items.{item_id}.location_id",
        )
        check(
            item.container_item_id,
            valid_item_ids,
            "unknown_item_id",
            f"items.{item_id}.container_item_id",
        )
        for index, holder_id in enumerate(item.holder_character_ids):
            check(
                holder_id,
                valid_character_ids,
                "unknown_character_id",
                f"items.{item_id}.holder_character_ids.{index}",
            )

    for cid, fact_ids in state.newly_known_fact_ids.items():
        check(
            cid,
            valid_character_ids,
            "unknown_character_id",
            f"newly_known_fact_ids.{cid}",
        )
        for index, fact_id in enumerate(fact_ids):
            check(
                fact_id,
                valid_fact_ids,
                "unknown_fact_id",
                f"newly_known_fact_ids.{cid}.{index}",
            )
    for index, loop_id in enumerate(state.active_open_loop_ids):
        check(
            loop_id,
            valid_open_loop_ids,
            "unknown_open_loop_id",
            f"active_open_loop_ids.{index}",
        )
    return issues


def _legacy_id_list(
    value: Any,
    *,
    allowed: Collection[str] | None,
    path: str,
    issues: list[ContinuityIssue],
) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for index, raw in enumerate(values):
        parsed = _id_or_none(raw, allowed=allowed)
        if parsed is None:
            issues.append(
                ContinuityIssue(
                    code="unmapped_legacy_value",
                    path=f"{path}.{index}",
                    value=_json_safe_copy(raw),
                )
            )
        elif parsed not in result:
            result.append(parsed)
    return result


def _legacy_injuries(
    value: Any,
    *,
    path: str,
    issues: list[ContinuityIssue],
) -> list[InjuryState]:
    if not isinstance(value, list):
        if value not in (None, ""):
            issues.append(
                ContinuityIssue(
                    code="unmapped_legacy_value",
                    path=path,
                    value=_json_safe_copy(value),
                )
            )
        return []
    injuries: list[InjuryState] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            issues.append(
                ContinuityIssue(
                    code="unmapped_legacy_value",
                    path=f"{path}.{index}",
                    value=_json_safe_copy(raw),
                )
            )
            continue
        try:
            injuries.append(InjuryState.model_validate(raw))
        except ValidationError:
            issues.append(
                ContinuityIssue(
                    code="unmapped_legacy_value",
                    path=f"{path}.{index}",
                    value=_json_safe_copy(raw),
                )
            )
    return injuries


def _normalise_legacy(
    raw: dict[str, Any],
    *,
    valid_character_ids: Collection[str] | None,
    valid_location_ids: Collection[str] | None,
    valid_item_ids: Collection[str] | None,
    valid_fact_ids: Collection[str] | None,
    valid_open_loop_ids: Collection[str] | None,
    valid_event_ids: Collection[str] | None,
) -> tuple[TypedContinuityState, list[ContinuityIssue]]:
    issues: list[ContinuityIssue] = []
    characters: dict[str, CharacterContinuity] = {}
    raw_characters = raw.get("characters") or {}
    if isinstance(raw_characters, dict):
        for raw_key, raw_state in raw_characters.items():
            if not isinstance(raw_state, dict):
                issues.append(
                    ContinuityIssue(
                        code="unmapped_legacy_value",
                        path=f"characters.{raw_key}",
                        value=_json_safe_copy(raw_state),
                    )
                )
                continue
            cid = _id_or_none(
                raw_state.get("character_id", raw_key),
                allowed=valid_character_ids,
            )
            if cid is None:
                issues.append(
                    ContinuityIssue(
                        code="unmapped_legacy_value",
                        path=f"characters.{raw_key}.character_id",
                        value=_json_safe_copy(
                            raw_state.get("character_id", raw_key)
                        ),
                    )
                )
                continue
            raw_location = raw_state.get(
                "location_id", raw_state.get("location")
            )
            location_id = _id_or_none(
                raw_location,
                allowed=valid_location_ids,
            )
            if raw_location not in (None, "") and location_id is None:
                issues.append(
                    ContinuityIssue(
                        code="unmapped_legacy_value",
                        path=f"characters.{cid}.location",
                        value=_json_safe_copy(raw_location),
                    )
                )
            movement = raw_state.get("movement_status", "unknown")
            if movement not in {
                "stationary",
                "departing",
                "in_transit",
                "arrived",
                "unknown",
            }:
                movement = "unknown"
                issues.append(
                    ContinuityIssue(
                        code="unmapped_legacy_value",
                        path=f"characters.{cid}.movement_status",
                        value=_json_safe_copy(raw_state.get("movement_status")),
                    )
                )
            alive = raw_state.get("alive_status", raw_state.get("status", "unknown"))
            if alive not in {"alive", "dead", "missing", "unknown"}:
                alive = "unknown"
                if raw_state.get("alive_status") or raw_state.get("status"):
                    issues.append(
                        ContinuityIssue(
                            code="unmapped_legacy_value",
                            path=f"characters.{cid}.alive_status",
                            value=_json_safe_copy(
                                raw_state.get(
                                    "alive_status", raw_state.get("status")
                                )
                            ),
                        )
                    )
            characters[cid] = CharacterContinuity(
                character_id=cid,
                location_id=location_id,
                movement_status=movement,
                destination_location_id=_id_or_none(
                    raw_state.get("destination_location_id"),
                    allowed=valid_location_ids,
                ),
                alive_status=alive,
                injuries=_legacy_injuries(
                    raw_state.get("injuries"),
                    path=f"characters.{cid}.injuries",
                    issues=issues,
                ),
                supporting_character_ids=_legacy_id_list(
                    raw_state.get("supporting_character_ids"),
                    allowed=valid_character_ids,
                    path=f"characters.{cid}.supporting_character_ids",
                    issues=issues,
                ),
                carried_by_character_id=_id_or_none(
                    raw_state.get("carried_by_character_id"),
                    allowed=valid_character_ids,
                ),
                knowledge_fact_ids=_legacy_id_list(
                    raw_state.get("knowledge_fact_ids"),
                    allowed=valid_fact_ids,
                    path=f"characters.{cid}.knowledge_fact_ids",
                    issues=issues,
                ),
            )

    items: dict[str, ItemContinuity] = {}
    raw_items = raw.get("items") or {}
    if isinstance(raw_items, dict):
        for raw_key, raw_state in raw_items.items():
            if not isinstance(raw_state, dict):
                issues.append(
                    ContinuityIssue(
                        code="unmapped_legacy_value",
                        path=f"items.{raw_key}",
                        value=_json_safe_copy(raw_state),
                    )
                )
                continue
            item_id = _id_or_none(
                raw_state.get("item_id", raw_key), allowed=valid_item_ids
            )
            if item_id is None:
                issues.append(
                    ContinuityIssue(
                        code="unmapped_legacy_value",
                        path=f"items.{raw_key}.item_id",
                        value=_json_safe_copy(raw_state.get("item_id", raw_key)),
                    )
                )
                continue
            raw_holders = raw_state.get(
                "holder_character_ids", raw_state.get("holder")
            )
            condition = raw_state.get("condition", "unknown")
            if condition not in {
                "intact",
                "damaged",
                "destroyed",
                "consumed",
                "partial",
                "unknown",
            }:
                condition = "unknown"
                issues.append(
                    ContinuityIssue(
                        code="unmapped_legacy_value",
                        path=f"items.{item_id}.condition",
                        value=_json_safe_copy(raw_state.get("condition")),
                    )
                )
            quantity = raw_state.get("quantity")
            if (
                isinstance(quantity, bool)
                or quantity is not None
                and (
                    not isinstance(quantity, (int, float))
                    or not math.isfinite(float(quantity))
                    or quantity < 0
                )
            ):
                issues.append(
                    ContinuityIssue(
                        code="unmapped_legacy_value",
                        path=f"items.{item_id}.quantity",
                        value=_json_safe_copy(quantity),
                    )
                )
                quantity = None
            items[item_id] = ItemContinuity(
                item_id=item_id,
                holder_character_ids=_legacy_id_list(
                    raw_holders,
                    allowed=valid_character_ids,
                    path=f"items.{item_id}.holder_character_ids",
                    issues=issues,
                ),
                location_id=_id_or_none(
                    raw_state.get("location_id", raw_state.get("location")),
                    allowed=valid_location_ids,
                ),
                quantity=quantity,
                condition=condition,
                container_item_id=_id_or_none(
                    raw_state.get("container_item_id"), allowed=valid_item_ids
                ),
            )

    newly_known: dict[str, list[str]] = {}
    raw_newly_known = raw.get("newly_known_fact_ids") or {}
    if isinstance(raw_newly_known, dict):
        for raw_cid, raw_fact_ids in raw_newly_known.items():
            cid = _id_or_none(raw_cid, allowed=valid_character_ids)
            if cid is None:
                issues.append(
                    ContinuityIssue(
                        code="unmapped_legacy_value",
                        path=f"newly_known_fact_ids.{raw_cid}",
                        value=_json_safe_copy(raw_fact_ids),
                    )
                )
                continue
            newly_known[cid] = _legacy_id_list(
                raw_fact_ids,
                allowed=valid_fact_ids,
                path=f"newly_known_fact_ids.{cid}",
                issues=issues,
            )

    raw_knowledge = raw.get("knowledge")
    if raw_knowledge:
        issues.append(
            ContinuityIssue(
                code="unmapped_legacy_value",
                path="knowledge",
                value=_json_safe_copy(raw_knowledge),
            )
        )

    active_loops = _legacy_id_list(
        raw.get("active_open_loop_ids"),
        allowed=valid_open_loop_ids,
        path="active_open_loop_ids",
        issues=issues,
    )
    time_marker = raw.get("time_marker", "")
    if not isinstance(time_marker, str):
        issues.append(
            ContinuityIssue(
                code="unmapped_legacy_value",
                path="time_marker",
                value=_json_safe_copy(time_marker),
            )
        )
        time_marker = ""
    state = TypedContinuityState(
        time_marker=time_marker[:300],
        characters=characters,
        items=items,
        newly_known_fact_ids=newly_known,
        active_open_loop_ids=active_loops,
    )
    issues.extend(
        validate_continuity_references(
            state,
            valid_character_ids=valid_character_ids,
            valid_location_ids=valid_location_ids,
            valid_item_ids=valid_item_ids,
            valid_fact_ids=valid_fact_ids,
            valid_open_loop_ids=valid_open_loop_ids,
            valid_event_ids=valid_event_ids,
        )
    )
    return state, issues


def normalise_continuity_state(
    value: Any,
    *,
    valid_character_ids: Collection[str] | None = None,
    valid_location_ids: Collection[str] | None = None,
    valid_item_ids: Collection[str] | None = None,
    valid_fact_ids: Collection[str] | None = None,
    valid_open_loop_ids: Collection[str] | None = None,
    valid_event_ids: Collection[str] | None = None,
) -> ContinuityNormalizationResult:
    """Return a typed view without guessing or mutating the raw payload.

    Typed payloads are eligible to be authoritative only when every reference
    catalog was supplied and no reference issue was found.  Legacy payloads are
    always non-authoritative, even when some stable IDs can be copied safely.
    """

    raw_payload = _json_safe_copy(value)
    catalogs = (
        valid_character_ids,
        valid_location_ids,
        valid_item_ids,
        valid_fact_ids,
        valid_open_loop_ids,
        valid_event_ids,
    )
    references_checked = all(catalog is not None for catalog in catalogs)
    if not isinstance(value, dict):
        return ContinuityNormalizationResult(
            source_schema="invalid",
            typed_state=TypedContinuityState(),
            raw_payload=raw_payload,
            issues=[
                ContinuityIssue(
                    code="invalid_typed_payload", path="$", value=raw_payload
                )
            ],
            authoritative_eligible=False,
            references_checked=references_checked,
        )

    if "schema_version" in value:
        try:
            state = TypedContinuityState.model_validate(value)
        except ValidationError:
            return ContinuityNormalizationResult(
                source_schema="invalid",
                typed_state=TypedContinuityState(),
                raw_payload=raw_payload,
                issues=[
                    ContinuityIssue(
                        code="invalid_typed_payload", path="$", value=None
                    )
                ],
                authoritative_eligible=False,
                references_checked=references_checked,
            )
        issues = validate_continuity_references(
            state,
            valid_character_ids=valid_character_ids,
            valid_location_ids=valid_location_ids,
            valid_item_ids=valid_item_ids,
            valid_fact_ids=valid_fact_ids,
            valid_open_loop_ids=valid_open_loop_ids,
            valid_event_ids=valid_event_ids,
        )
        return ContinuityNormalizationResult(
            source_schema="typed_v1",
            typed_state=state,
            raw_payload=raw_payload,
            issues=issues,
            authoritative_eligible=references_checked and not issues,
            references_checked=references_checked,
        )

    state, issues = _normalise_legacy(
        value,
        valid_character_ids=valid_character_ids,
        valid_location_ids=valid_location_ids,
        valid_item_ids=valid_item_ids,
        valid_fact_ids=valid_fact_ids,
        valid_open_loop_ids=valid_open_loop_ids,
        valid_event_ids=valid_event_ids,
    )
    return ContinuityNormalizationResult(
        source_schema="legacy",
        typed_state=state,
        raw_payload=raw_payload,
        issues=issues,
        authoritative_eligible=False,
        references_checked=references_checked,
    )


__all__ = [
    "AliveStatus",
    "CharacterContinuity",
    "ContinuityIssue",
    "ContinuityNormalizationResult",
    "InjurySeverity",
    "InjuryState",
    "InjuryStatus",
    "ItemCondition",
    "ItemContinuity",
    "MovementStatus",
    "TypedContinuityState",
    "normalise_continuity_state",
    "validate_continuity_references",
]
