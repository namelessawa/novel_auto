"""
跨模块共享的领域模型 (Entity / Relation / Snapshot 等)。

这些类型供 `knowledge_graph.py` 与 (未来的) `agent_backend` 使用。
旧的 `entity_state.py` / `character_relationship.py` 没有用强类型 model，仍以 dict
形式工作，保持向后兼容；新模块通过 `from memory_system.models import ...` 引入。
"""

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
class GraphSnapshot:
    snapshot_id: str
    chapter: int
    timestamp: str
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)


@dataclass(frozen=True)
class Section:
    chapter: int
    section: int
    title: str
    content: str
    summary: str = ""
    word_count: int = 0


@dataclass(frozen=True)
class ActionPlan:
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


__all__ = [
    "EntityType",
    "RelationType",
    "Entity",
    "Relation",
    "GraphSnapshot",
    "Section",
    "ActionPlan",
    "ValidationResult",
]
