"""Deterministic prose contract models and builder for author mode.

The Writer never decides which facts are mandatory.  This module derives a
frozen contract from the four author authorities plus structured user input:
StoryBible, CanonicalState, SectionGoal and the selected StoryThreads.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Severity = Literal["low", "medium", "high"]
EventCompletionState = Literal[
    "missing",
    "mentioned",
    "started",
    "attempted",
    "completed",
    "contradicted",
    "wrong_actor",
    "wrong_target",
]


class NarrativeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EntityReference(NarrativeModel):
    id: str = Field(min_length=1)
    name: str = ""
    aliases: list[str] = Field(default_factory=list)
    max_count: int = Field(default=1, ge=1)

    @field_validator("aliases")
    @classmethod
    def _unique_aliases(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @property
    def all_names(self) -> list[str]:
        return list(dict.fromkeys([self.id, self.name, *self.aliases]))


class AllowedEntities(NarrativeModel):
    characters: list[EntityReference] = Field(default_factory=list)
    locations: list[EntityReference] = Field(default_factory=list)
    items: list[EntityReference] = Field(default_factory=list)
    organizations: list[EntityReference] = Field(default_factory=list)
    generic_terms: list[str] = Field(default_factory=list)

    @field_validator(
        "characters", "locations", "items", "organizations", mode="before"
    )
    @classmethod
    def _normalise_entities(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        values = value if isinstance(value, (list, tuple)) else [value]
        return [
            {"id": item, "name": item} if isinstance(item, str) else item
            for item in values
        ]

    @field_validator("generic_terms")
    @classmethod
    def _unique_terms(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class RequiredFact(NarrativeModel):
    id: str = Field(min_length=1)
    subject: str = ""
    predicate: str = ""
    object: str = ""
    time: str = ""
    statement: str = ""
    required_in_prose: bool = True
    evidence_patterns: list[str] = Field(default_factory=list)
    mutation_patterns: list[str] = Field(default_factory=list)
    contradiction_patterns: list[str] = Field(default_factory=list)


class RequiredEvent(NarrativeModel):
    id: str = Field(min_length=1)
    actor: str = ""
    action: str = Field(min_length=1)
    target: str = ""
    description: str = ""
    required_evidence: bool = True
    evidence_patterns: list[str] = Field(default_factory=list)
    incomplete_patterns: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    min_keyword_matches: int = Field(default=1, ge=1)


class RequiredEndState(NarrativeModel):
    id: str = Field(min_length=1)
    path: str = Field(min_length=2, pattern=r"^/")
    expected: Any
    description: str = ""
    evidence_patterns: list[str] = Field(default_factory=list)
    wrong_state_patterns: list[str] = Field(default_factory=list)


class TimeConstraint(NarrativeModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    deadline: str = ""
    required_patterns: list[str] = Field(default_factory=list)
    mutation_patterns: list[str] = Field(default_factory=list)
    causal_patterns: list[str] = Field(default_factory=list)
    weakened_patterns: list[str] = Field(default_factory=list)


class ForbiddenAddition(NarrativeModel):
    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    code: str = ""
    patterns: list[str] = Field(default_factory=list)
    allowed_patterns: list[str] = Field(default_factory=list)
    severity: Severity = "high"


class ForbiddenOutcome(NarrativeModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    patterns: list[str] = Field(default_factory=list)
    severity: Severity = "high"


class ProtectedRelationship(NarrativeModel):
    id: str = Field(min_length=1)
    parties: list[str] = Field(min_length=2)
    relationship: str = ""
    forbidden_patterns: list[str] = Field(default_factory=list)


class ProtectedCausalLink(NarrativeModel):
    id: str = Field(min_length=1)
    cause: str = Field(min_length=1)
    effect: str = Field(min_length=1)
    required_patterns: list[str] = Field(default_factory=list)
    weakened_patterns: list[str] = Field(default_factory=list)


class LengthConstraint(NarrativeModel):
    min_chars: int = Field(default=200, ge=1)
    max_chars: int = Field(default=3000, ge=1)

    @field_validator("max_chars")
    @classmethod
    def _positive_max(cls, value: int) -> int:
        return max(1, value)


class NarrativeContractInput(NarrativeModel):
    """Structured user constraints; empty input preserves existing API clients."""

    allowed_entities: AllowedEntities = Field(default_factory=AllowedEntities)
    required_facts: list[RequiredFact] = Field(default_factory=list)
    required_events: list[RequiredEvent] = Field(default_factory=list)
    required_end_state: list[RequiredEndState] = Field(default_factory=list)
    time_constraints: list[TimeConstraint] = Field(default_factory=list)
    forbidden_additions: list[ForbiddenAddition] = Field(default_factory=list)
    forbidden_outcomes: list[ForbiddenOutcome] = Field(default_factory=list)
    protected_relationships: list[ProtectedRelationship] = Field(default_factory=list)
    protected_causal_links: list[ProtectedCausalLink] = Field(default_factory=list)
    length_constraint: LengthConstraint | None = None


class NarrativeContract(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    section_id: str = Field(min_length=1)
    story_bible_revision: int = Field(ge=1)
    canonical_state_revision: int = Field(ge=1)
    allowed_entities: AllowedEntities = Field(default_factory=AllowedEntities)
    required_facts: list[RequiredFact] = Field(default_factory=list)
    required_events: list[RequiredEvent] = Field(default_factory=list)
    required_end_state: list[RequiredEndState] = Field(default_factory=list)
    time_constraints: list[TimeConstraint] = Field(default_factory=list)
    forbidden_additions: list[ForbiddenAddition] = Field(default_factory=list)
    forbidden_outcomes: list[ForbiddenOutcome] = Field(default_factory=list)
    protected_relationships: list[ProtectedRelationship] = Field(default_factory=list)
    protected_causal_links: list[ProtectedCausalLink] = Field(default_factory=list)
    length_constraint: LengthConstraint = Field(default_factory=LengthConstraint)
    style_priority: Literal["subordinate_to_facts"] = "subordinate_to_facts"
    source_summary: list[str] = Field(default_factory=list)
    contract_hash: str = ""


class NarrativeViolation(NarrativeModel):
    code: str
    message: str
    severity: Severity
    path: str = ""
    evidence: str = ""
    repair_hint: str = ""


class EndStateResult(NarrativeModel):
    id: str
    path: str
    expected: Any
    reached: bool = False
    evidence: str = ""
    violation_code: str = ""


class EventCompletionResult(NarrativeModel):
    event_id: str
    status: EventCompletionState = "missing"
    evidence: str = ""
    actor_matched: bool = False
    target_matched: bool = False
    action_matched: bool = False
    evidence_hint_matched: bool = False
    violation_code: str = ""


class NarrativeValidationReport(NarrativeModel):
    accepted: bool = False
    severity: Severity = "low"
    violations: list[NarrativeViolation] = Field(default_factory=list)
    missing_required_events: list[str] = Field(default_factory=list)
    unsupported_additions: list[str] = Field(default_factory=list)
    event_results: list[EventCompletionResult] = Field(default_factory=list)
    end_state_results: list[EndStateResult] = Field(default_factory=list)
    contract_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    required_fact_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    required_event_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    required_end_state_coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    narrative_char_count: int = Field(default=0, ge=0)
    repairable: bool = True


DEFAULT_FORBIDDEN_ADDITIONS = (
    ("unsupported_number", "number", "未授权的事实性数字"),
    ("unsupported_date", "date", "未授权的具体日期或时间点"),
    ("unsupported_kinship", "kinship", "未授权的亲属关系"),
    ("unsupported_casualty", "casualty", "未授权的伤亡数字"),
    ("unsupported_injury", "injury", "未授权的新暴力或伤势"),
    ("unsupported_backstory", "backstory", "未授权的人物年龄或经历"),
    ("unsupported_entity", "entity", "未授权的人物、组织或责任主体"),
)


def narrative_char_count(text: str) -> int:
    """Single backend/frontend contract metric: all non-whitespace characters."""
    return sum(1 for char in text if not char.isspace())


def narrative_contract_prompt_payload(contract: NarrativeContract) -> dict[str, Any]:
    """Validation patterns stay server-side; Writer sees only contract semantics."""
    return {
        "contract_hash": contract.contract_hash,
        "authority": "NarrativeContract > StoryBible/CanonicalState > StyleContract",
        "allowed_entities": {
            name: [
                {
                    "id": item.id,
                    "name": item.name,
                    "aliases": item.aliases,
                    "max_count": item.max_count,
                }
                for item in getattr(contract.allowed_entities, name)
            ]
            for name in ("characters", "locations", "items", "organizations")
        },
        "allowed_generic_terms": contract.allowed_entities.generic_terms,
        "required_facts": [
            {
                "id": item.id,
                "subject": item.subject,
                "predicate": item.predicate,
                "object": item.object,
                "time": item.time,
                "statement": item.statement,
                "required_in_prose": item.required_in_prose,
            }
            for item in contract.required_facts
        ],
        "required_events": [
            {
                "id": item.id,
                "actor": item.actor,
                "action": item.action,
                "target": item.target,
                "description": item.description,
            }
            for item in contract.required_events
        ],
        "required_end_state": [
            {
                "id": item.id,
                "path": item.path,
                "expected": item.expected,
                "description": item.description,
            }
            for item in contract.required_end_state
        ],
        "time_constraints": [
            {"id": item.id, "description": item.description, "deadline": item.deadline}
            for item in contract.time_constraints
        ],
        "forbidden_additions": [item.description for item in contract.forbidden_additions],
        "forbidden_outcomes": [item.description for item in contract.forbidden_outcomes],
        "protected_relationships": [
            {
                "parties": item.parties,
                "relationship": item.relationship,
            }
            for item in contract.protected_relationships
        ],
        "protected_causal_links": [
            {"cause": item.cause, "effect": item.effect}
            for item in contract.protected_causal_links
        ],
        "length_constraint": contract.length_constraint.model_dump(mode="json"),
        "style_priority": contract.style_priority,
    }


def _entity(value: Any, identifier: str) -> EntityReference:
    payload = value if isinstance(value, dict) else {}
    name = str(payload.get("name") or identifier)
    aliases = [str(item) for item in payload.get("aliases", []) if str(item).strip()]
    return EntityReference(id=identifier, name=name, aliases=aliases)


def _world_entities(world: dict[str, Any], key: str) -> list[EntityReference]:
    raw = world.get(key, [])
    if isinstance(raw, dict):
        return [_entity(value, str(identifier)) for identifier, value in raw.items()]
    out: list[EntityReference] = []
    if isinstance(raw, list):
        for value in raw:
            if isinstance(value, dict):
                identifier = str(value.get("id") or value.get("name") or "")
                if identifier:
                    out.append(_entity(value, identifier))
            elif value:
                out.append(EntityReference(id=str(value), name=str(value)))
    return out


def _merge_entities(
    derived: list[EntityReference], explicit: list[EntityReference]
) -> list[EntityReference]:
    merged: dict[str, EntityReference] = {item.id: item for item in derived}
    for item in explicit:
        previous = merged.get(item.id)
        if previous is None:
            merged[item.id] = item
            continue
        merged[item.id] = previous.model_copy(
            update={
                "name": item.name or previous.name,
                "aliases": list(dict.fromkeys(previous.aliases + item.aliases)),
                "max_count": item.max_count,
            }
        )
    return list(merged.values())


def _objective_keywords(objective: str) -> list[str]:
    chunks = re.split(r"[，。！？；：、,/|\s与和并且让使将把的了]+", objective)
    chunks = [item for item in chunks if 2 <= len(item) <= 16]
    return list(dict.fromkeys(chunks))[:8]


class NarrativeContractBuilder:
    """Build a reproducible contract without an LLM or post-hoc inference."""

    def build(
        self,
        *,
        story_bible: Any,
        canonical_state: Any,
        section_goal: Any,
        story_threads: list[Any],
        require_default_objective_event: bool = True,
    ) -> NarrativeContract:
        explicit = section_goal.narrative_constraints
        character_ids = set(section_goal.involved_characters)
        if section_goal.viewpoint_character_id:
            character_ids.add(section_goal.viewpoint_character_id)
        if not character_ids:
            character_ids.update(canonical_state.characters)
        characters = [
            _entity(canonical_state.characters[item], item)
            for item in sorted(character_ids)
            if item in canonical_state.characters
        ]
        locations = _world_entities(canonical_state.world, "locations")
        organizations = _world_entities(canonical_state.world, "organizations")
        items = [
            _entity(value, str(identifier))
            for identifier, value in sorted(canonical_state.items.items())
        ]
        allowed = AllowedEntities(
            characters=_merge_entities(
                characters, explicit.allowed_entities.characters
            ),
            locations=_merge_entities(
                locations, explicit.allowed_entities.locations
            ),
            items=_merge_entities(items, explicit.allowed_entities.items),
            organizations=_merge_entities(
                organizations, explicit.allowed_entities.organizations
            ),
            generic_terms=list(
                dict.fromkeys(
                    [
                        "他",
                        "她",
                        "其",
                        "对方",
                        "路人",
                        *explicit.allowed_entities.generic_terms,
                    ]
                )
            ),
        )

        facts = list(explicit.required_facts)
        for fact_id, payload in canonical_state.canonical_facts.items():
            if not isinstance(payload, dict):
                continue
            subject = str(payload.get("subject") or "")
            obj = str(payload.get("object") or payload.get("value") or "")
            if character_ids and subject not in character_ids and obj not in character_ids:
                continue
            facts.append(
                RequiredFact(
                    id=f"canonical_{fact_id}",
                    subject=subject,
                    predicate=str(payload.get("predicate") or payload.get("relation") or ""),
                    object=obj,
                    time=str(payload.get("time") or ""),
                    statement=str(payload.get("statement") or payload.get("description") or ""),
                    required_in_prose=False,
                )
            )

        events = list(explicit.required_events)
        if not events and require_default_objective_event:
            keywords = _objective_keywords(section_goal.objective)
            events.append(
                RequiredEvent(
                    id="section_goal_objective",
                    actor=section_goal.viewpoint_character_id,
                    action=section_goal.objective,
                    description=section_goal.objective,
                    keywords=keywords,
                    min_keyword_matches=min(2, max(1, len(keywords))),
                )
            )

        selected_threads = {
            item.id: item for item in story_threads if item.id in section_goal.target_threads
        }
        for thread in selected_threads.values():
            for index, requirement in enumerate(thread.resolution_requirements):
                facts.append(
                    RequiredFact(
                        id=f"thread_{thread.id}_{index}",
                        statement=requirement,
                        required_in_prose=True,
                        evidence_patterns=[re.escape(requirement)],
                    )
                )
            if (
                thread.id in section_goal.liveness_required_threads
                and thread.advance_condition
            ):
                keywords = _objective_keywords(thread.advance_condition)
                events.append(
                    RequiredEvent(
                        id=f"thread_advance_{thread.id}",
                        actor="",
                        action=thread.advance_condition,
                        description=(
                            f"推进故事线 {thread.id}: {thread.advance_condition}"
                        ),
                        evidence_patterns=[re.escape(thread.advance_condition)],
                        keywords=keywords,
                        min_keyword_matches=min(2, max(1, len(keywords))),
                    )
                )

        relationships = list(explicit.protected_relationships)
        for key, value in canonical_state.relationships.items():
            parties = [part for part in re.split(r"[:|/]", str(key)) if part]
            if len(parties) < 2 or not set(parties).intersection(character_ids):
                continue
            description = (
                str(value.get("description") or value)
                if isinstance(value, dict)
                else str(value)
            )
            relationships.append(
                ProtectedRelationship(
                    id=f"canonical_relationship_{key}",
                    parties=parties,
                    relationship=description,
                )
            )

        additions = [
            ForbiddenAddition(id=item[0], category=item[1], description=item[2])
            for item in DEFAULT_FORBIDDEN_ADDITIONS
        ]
        additions.extend(explicit.forbidden_additions)
        length = explicit.length_constraint or LengthConstraint(
            min_chars=200,
            max_chars=max(300, int(section_goal.desired_length * 1.5)),
        )
        if length.max_chars < length.min_chars:
            length = length.model_copy(update={"max_chars": length.min_chars})

        contract = NarrativeContract(
            section_id=section_goal.section_id,
            story_bible_revision=story_bible.revision,
            canonical_state_revision=canonical_state.revision,
            allowed_entities=allowed,
            required_facts=facts,
            required_events=events,
            required_end_state=explicit.required_end_state,
            time_constraints=explicit.time_constraints,
            forbidden_additions=additions,
            forbidden_outcomes=explicit.forbidden_outcomes,
            protected_relationships=relationships,
            protected_causal_links=explicit.protected_causal_links,
            length_constraint=length,
            source_summary=[
                f"StoryBible@{story_bible.revision}",
                f"CanonicalState@{canonical_state.revision}",
                f"SectionGoal:{section_goal.section_id}",
                *[f"StoryThread:{item}" for item in section_goal.target_threads],
                "StructuredUserConstraints",
            ],
        )
        payload = contract.model_dump(mode="json", exclude={"contract_hash"})
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return contract.model_copy(update={"contract_hash": digest})


__all__ = [
    "AllowedEntities",
    "EndStateResult",
    "EventCompletionResult",
    "EntityReference",
    "ForbiddenAddition",
    "ForbiddenOutcome",
    "LengthConstraint",
    "NarrativeContract",
    "NarrativeContractBuilder",
    "NarrativeContractInput",
    "NarrativeValidationReport",
    "NarrativeViolation",
    "ProtectedCausalLink",
    "ProtectedRelationship",
    "RequiredEndState",
    "RequiredEvent",
    "RequiredFact",
    "TimeConstraint",
    "narrative_char_count",
    "narrative_contract_prompt_payload",
]
