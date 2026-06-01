"""Shared domain models used across all modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
    SKILL = "skill"
    FACTION = "faction"


class RelationType(str, Enum):
    LOCATED_AT = "located_at"
    HOLDS = "holds"
    KNOWS = "knows"
    HOSTILE = "hostile"
    ALLIED = "allied"
    LOVES = "loves"
    PARENT_OF = "parent_of"
    MEMBER_OF = "member_of"
    MASTER_OF = "master_of"
    CUSTOM = "custom"


@dataclass(frozen=True)
class Entity:
    id: str
    name: str
    entity_type: EntityType
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Relation:
    source_id: str
    target_id: str
    relation_type: RelationType
    label: str = ""
    weight: float = 1.0
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Section:
    """A single section of generated novel text."""
    chapter: int
    section: int
    title: str
    content: str
    summary: str = ""
    word_count: int = 0


@dataclass(frozen=True)
class ActionPlan:
    """The 100-word action guide for the next section."""
    chapter: int
    section: int
    plan_text: str
    key_entities: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    conflicts: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphSnapshot:
    snapshot_id: str
    chapter: int
    timestamp: str
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
