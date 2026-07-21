"""Deterministic projections from existing tick contracts to CanonicalFact.

No natural-language extraction is performed here.  The projector observes
accepted before/after state, typed Event metadata and the guarded continuity
schema.  Callers may persist the returned records to the sidecar or merely use
them for audit fixtures.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Iterable

from memory_system.models import (
    CharacterAction,
    CharacterState,
    Event,
    OpenLoop,
    WorldState,
)
from narrative.canonical_facts import (
    CanonicalFact,
    CanonicalFactStore,
    FactSourceKind,
    FactSourceRef,
    build_canonical_fact,
)
from narrative.typed_continuity import continuity_legacy_view


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _source_refs(
    *,
    kind: FactSourceKind,
    source_id: str,
    tick: int,
    path: str = "",
) -> list[FactSourceRef]:
    return [FactSourceRef(kind=kind, source_id=source_id, tick=tick, path=path)]


def _item_subject(item: str) -> str:
    # Existing inventories contain names rather than entity IDs.  Prefixing
    # keeps the namespace explicit without pretending two equal names are two
    # distinguishable instances.
    return f"item:{item.strip()}"


@dataclass
class ProjectionResult:
    facts: list[CanonicalFact] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def extend(self, other: "ProjectionResult") -> None:
        self.facts.extend(other.facts)
        self.skipped.extend(other.skipped)


def project_event(event: Event) -> ProjectionResult:
    """Record occurrence and visibility without interpreting consequences."""

    fact = build_canonical_fact(
        subject_id=event.id,
        predicate="event_occurred",
        value={
            "type": event.type,
            "location": event.location,
            "participants": list(event.participants),
            "description": event.description,
        },
        valid_from_tick=event.tick,
        source_event_ids=[event.id],
        known_by=event.visible_to,
        status="historical",
        reversible=False,
    )
    return ProjectionResult(facts=[fact])


def project_character_transition(
    before: CharacterState,
    after: CharacterState,
    *,
    tick: int,
    source_kind: FactSourceKind,
    source_id: str,
    source_event_ids: Iterable[str] = (),
) -> ProjectionResult:
    """Project only fields whose accepted CharacterState value changed."""

    if before.character_id != after.character_id:
        raise ValueError("character transition IDs do not match")
    cid = after.character_id
    refs = _source_refs(
        kind=source_kind, source_id=source_id, tick=tick
    )
    event_ids = list(source_event_ids)
    result = ProjectionResult()

    def add(
        subject_id: str,
        predicate: str,
        value: object,
        *,
        known_by: Iterable[str] = (),
        reversible: bool = True,
    ) -> None:
        result.facts.append(
            build_canonical_fact(
                subject_id=subject_id,
                predicate=predicate,
                value=value,
                valid_from_tick=tick,
                source_event_ids=event_ids,
                source_refs=refs,
                known_by=known_by,
                reversible=reversible,
            )
        )

    if before.current_location != after.current_location:
        value = (
            {"state": "arrived", "location_id": after.current_location}
            if after.current_location
            else {"state": "unknown", "location_id": None}
        )
        add(cid, "character_location", value)

    before_inventory = set(before.inventory)
    after_inventory = set(after.inventory)
    for item in sorted(after_inventory - before_inventory):
        add(_item_subject(item), "item_holder", cid)
    for item in sorted(before_inventory - after_inventory):
        add(
            _item_subject(item),
            "item_holder",
            None,
        )

    before_status = set(before.status_effects)
    after_status = set(after.status_effects)
    for status in sorted(after_status - before_status):
        add(cid, f"status_effect:{status}", True)
    for status in sorted(before_status - after_status):
        add(cid, f"status_effect:{status}", False)
    before_dead = "dead" in before_status
    after_dead = "dead" in after_status
    if before_dead != after_dead:
        add(
            cid,
            "alive_status",
            "dead" if after_dead else "alive",
            reversible=not after_dead,
        )

    before_known = set(before.known_facts)
    for learned in sorted(set(after.known_facts) - before_known):
        predicate = f"character_knows:{_digest(learned)}"
        add(
            cid,
            predicate,
            {"proposition": learned, "epistemic": "known"},
            known_by=[cid],
            reversible=False,
        )

    relation_ids = set(before.relationships) | set(after.relationships)
    for other_id in sorted(relation_ids):
        old = before.relationships.get(other_id)
        new = after.relationships.get(other_id)
        if new is None:
            continue
        if old is None or old.type != new.type:
            add(cid, f"relationship_state:{other_id}", new.type)
        if old is None or old.trust != new.trust:
            add(cid, f"trust:{other_id}", new.trust)

    if before.money != after.money:
        add(cid, "money_balance", after.money)

    return result


def project_world_transition(
    before: WorldState,
    after: WorldState,
    *,
    tick: int,
    source_kind: FactSourceKind,
    source_id: str,
    source_event_ids: Iterable[str] = (),
) -> ProjectionResult:
    """Project typed world fields; do not parse free-form event prose."""

    refs = _source_refs(kind=source_kind, source_id=source_id, tick=tick)
    event_ids = list(source_event_ids)
    result = ProjectionResult()

    def add(subject: str, predicate: str, value: object) -> None:
        result.facts.append(
            build_canonical_fact(
                subject_id=subject,
                predicate=predicate,
                value=value,
                valid_from_tick=tick,
                source_event_ids=event_ids,
                source_refs=refs,
            )
        )

    for field_name in (
        "world_time",
        "era",
        "current_season",
        "weather",
        "active_global_events",
        "world_rules",
    ):
        if getattr(before, field_name) != getattr(after, field_name):
            add("world", field_name, getattr(after, field_name))

    old_locations = {location.id: location for location in before.locations}
    for location in after.locations:
        old = old_locations.get(location.id)
        if old is None or old.current_state != location.current_state:
            add(location.id, "location_state", location.current_state)
    return result


def project_character_epistemics(
    action: CharacterAction,
    *,
    tick: int,
    source_event_ids: Iterable[str] = (),
) -> ProjectionResult:
    """Persist explicit speculation as belief, never as objective knowledge."""

    result = ProjectionResult()
    event_ids = list(source_event_ids)
    refs = _source_refs(
        kind="state_transition",
        source_id=f"character_action:{tick}:{action.character_id}",
        tick=tick,
    )
    for proposition in sorted(set(action.newly_speculated)):
        if not proposition.strip():
            continue
        result.facts.append(
            build_canonical_fact(
                subject_id=action.character_id,
                predicate=f"character_believes:{_digest(proposition)}",
                value={
                    "proposition": proposition,
                    "epistemic": "belief",
                },
                valid_from_tick=tick,
                source_event_ids=event_ids,
                source_refs=refs,
                known_by=[action.character_id],
                status="belief",
                confidence=0.5,
            )
        )
    return result


def project_guarded_continuity_state(
    continuity_state: dict,
    *,
    tick: int,
    consumed_event_ids: Iterable[str] = (),
    continuity_audit: dict | None = None,
) -> ProjectionResult:
    """Project only the documented characters/items/knowledge schema.

    Missing fields produce no update.  In particular, an omitted injury never
    produces a healing fact.  Unknown keys are retained only as diagnostics in
    ``skipped`` and cannot mutate current canonical state.
    """

    result = ProjectionResult()
    continuity_state = continuity_legacy_view(
        continuity_state, audit=continuity_audit
    )
    if not continuity_state:
        result.skipped.append("continuity_state_not_authoritative")
        return result
    event_ids = sorted(set(consumed_event_ids))
    refs = _source_refs(
        kind="guarded_narrative",
        source_id=f"narrative:{tick}",
        tick=tick,
    )

    def add(
        subject: str,
        predicate: str,
        value: object,
        *,
        known_by: Iterable[str] = (),
    ) -> None:
        result.facts.append(
            build_canonical_fact(
                subject_id=subject,
                predicate=predicate,
                value=value,
                valid_from_tick=tick,
                source_event_ids=event_ids,
                source_narrative_ticks=[tick],
                source_refs=refs,
                known_by=known_by,
            )
        )

    characters = continuity_state.get("characters", {})
    if isinstance(characters, dict):
        for raw_cid, raw_state in characters.items():
            cid = str(raw_cid).strip()
            if not cid or not isinstance(raw_state, dict):
                continue
            if "location" in raw_state:
                location = raw_state.get("location")
                add(
                    cid,
                    "character_location",
                    {
                        "state": "arrived" if location else "unknown",
                        "location_id": location or None,
                    },
                )
            injuries = raw_state.get("injuries")
            if isinstance(injuries, list):
                for injury in injuries:
                    if isinstance(injury, str) and injury.strip():
                        add(cid, f"injury:{injury.strip()}", True)
            for key in ("alive_status", "status"):
                if key in raw_state and raw_state.get(key) not in (None, ""):
                    add(cid, "alive_status", raw_state.get(key))

    items = continuity_state.get("items", {})
    if isinstance(items, dict):
        field_map = {
            "holder": "item_holder",
            "quantity": "item_quantity",
            "condition": "item_condition",
            "location": "item_location",
        }
        for raw_name, raw_state in items.items():
            name = str(raw_name).strip()
            if not name or not isinstance(raw_state, dict):
                continue
            subject = _item_subject(name)
            for raw_field, predicate in field_map.items():
                if raw_field in raw_state:
                    add(subject, predicate, raw_state.get(raw_field))

    knowledge = continuity_state.get("knowledge", [])
    if isinstance(knowledge, list):
        for item in knowledge:
            if not isinstance(item, dict):
                result.skipped.append("unstructured_continuity_knowledge")
                continue
            cid = str(
                item.get("character_id") or item.get("known_by") or ""
            ).strip()
            proposition = str(
                item.get("fact") or item.get("proposition") or ""
            ).strip()
            if not cid or not proposition:
                result.skipped.append("unattributed_continuity_knowledge")
                continue
            add(
                cid,
                f"character_knows:{_digest(proposition)}",
                {"proposition": proposition, "epistemic": "known"},
                known_by=[cid],
            )
    return result


def project_open_loop_resolution(
    loop: OpenLoop,
    *,
    tick: int,
    payoff_summary: str,
    evidence_event_ids: Iterable[str],
) -> ProjectionResult:
    event_ids = sorted(set(evidence_event_ids))
    fact = build_canonical_fact(
        subject_id=loop.id,
        predicate="open_loop_resolution",
        value={
            "promised_question": loop.promised_question or loop.description,
            "payoff_summary": payoff_summary.strip(),
            "evidence_event_ids": event_ids,
        },
        valid_from_tick=tick,
        source_event_ids=event_ids,
        source_refs=_source_refs(
            kind="open_loop_resolution",
            source_id=f"{loop.id}:{tick}",
            tick=tick,
        ),
        status="historical",
        reversible=False,
    )
    return ProjectionResult(facts=[fact])


def project_open_loop_resolution_record(record: dict) -> ProjectionResult:
    """Project the auditable record persisted by TickState.resolve_open_loop."""

    loop = OpenLoop(
        id=str(record.get("loop_id", "")),
        opened_tick=0,
        description=str(record.get("description", "") or "resolved loop"),
        promised_question=str(record.get("promised_question", "") or ""),
    )
    return project_open_loop_resolution(
        loop,
        tick=int(record.get("tick", 0)),
        payoff_summary=str(record.get("payoff_summary", "") or ""),
        evidence_event_ids=record.get("evidence_event_ids", []) or [],
    )


def append_projection(
    store: CanonicalFactStore, projection: ProjectionResult
) -> list[CanonicalFact]:
    return [store.append(fact) for fact in projection.facts]


def state_patch_source_id(payload: object) -> str:
    """Stable ID for a StatePatch when no source Event exists."""

    def normalize(value: object) -> object:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in value.items()}
        return value

    payload = normalize(payload)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"patch_{hashlib.sha256(encoded).hexdigest()[:20]}"


__all__ = [
    "ProjectionResult",
    "append_projection",
    "project_character_transition",
    "project_character_epistemics",
    "project_event",
    "project_guarded_continuity_state",
    "project_open_loop_resolution",
    "project_open_loop_resolution_record",
    "project_world_transition",
    "state_patch_source_id",
]
