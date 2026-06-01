#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Semantic Memory Module
Knowledge graph for characters, locations, rules, and relationships

Inspired by cognitive science semantic memory:
- Long-term storage of facts and concepts
- Relationship-based organization
- Consistency checking and inference
- Ontology for domain concepts

Key Features:
1. Knowledge Graph - Entities connected by typed relationships
2. Relationship Inference - Deduce implicit relationships
3. Consistency Checking - Validate assertions against known facts
4. Ontology Support - Domain-specific concept hierarchies
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import re


@dataclass
class Entity:
    """
    An entity in the knowledge graph

    Entities represent:
    - Characters
    - Locations
    - Objects
    - Concepts (themes, rules, etc.)
    """
    id: str
    name: str
    entity_type: str  # "character", "location", "object", "concept"
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_chapter: int = 1
    last_updated_chapter: int = 1
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            "attributes": self.attributes,
            "created_chapter": self.created_chapter,
            "last_updated_chapter": self.last_updated_chapter,
            "aliases": self.aliases,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Entity':
        return cls(
            id=data["id"],
            name=data["name"],
            entity_type=data["entity_type"],
            attributes=data.get("attributes", {}),
            created_chapter=data.get("created_chapter", 1),
            last_updated_chapter=data.get("last_updated_chapter", 1),
            aliases=data.get("aliases", []),
            metadata=data.get("metadata", {})
        )


@dataclass
class Relation:
    """
    A relationship between entities

    Relations are typed, directed connections:
    - character A -> friend_of -> character B
    - character A -> located_at -> location B
    - character A -> owns -> object B
    """
    id: str
    source_id: str
    target_id: str
    relation_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    established_chapter: int = 1
    last_updated_chapter: int = 1
    confidence: float = 1.0  # How confident we are in this relationship
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "properties": self.properties,
            "established_chapter": self.established_chapter,
            "last_updated_chapter": self.last_updated_chapter,
            "confidence": self.confidence,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Relation':
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            relation_type=data["relation_type"],
            properties=data.get("properties", {}),
            established_chapter=data.get("established_chapter", 1),
            last_updated_chapter=data.get("last_updated_chapter", 1),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {})
        )


@dataclass
class OntologyNode:
    """
    A node in the domain ontology

    Defines concept hierarchies:
    - character -> protagonist, antagonist, supporting
    - location -> indoor, outdoor
    - relationship -> familial, romantic, professional, hostile
    """
    concept: str
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


class SemanticMemory:
    """
    Semantic Memory with Knowledge Graph Structure

    Features:
    - Entity management with type system
    - Typed relationships between entities
    - Relationship inference engine
    - Consistency checking layer
    - Domain ontology support

    TTL: Permanent (updates dynamically)
    """

    # Default relation types and their inverses
    DEFAULT_RELATION_INVERSES = {
        "friend_of": "friend_of",
        "enemy_of": "enemy_of",
        "parent_of": "child_of",
        "child_of": "parent_of",
        "sibling_of": "sibling_of",
        "lover_of": "lover_of",
        "married_to": "married_to",
        "knows": "known_by",
        "located_at": "contains",
        "contains": "located_at",
        "owns": "owned_by",
        "owned_by": "owns",
        "works_at": "employer_of",
        "employer_of": "works_at",
    }

    # Transitive relations
    TRANSITIVE_RELATIONS = {"friend_of", "enemy_of", "knows"}

    def __init__(self, memory_dir: str = "memory_system"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Entities storage
        self._entities: Dict[str, Entity] = {}
        self._entity_by_name: Dict[str, str] = {}  # name -> id

        # Relations storage
        self._relations: Dict[str, Relation] = {}
        self._outgoing: Dict[str, List[str]] = defaultdict(list)  # source_id -> [relation_ids]
        self._incoming: Dict[str, List[str]] = defaultdict(list)  # target_id -> [relation_ids]
        self._relations_by_type: Dict[str, List[str]] = defaultdict(list)  # type -> [relation_ids]

        # Ontology
        self._ontology: Dict[str, OntologyNode] = {}
        self._init_default_ontology()

        # Current chapter
        self._current_chapter = 1

        # Counter for IDs
        self._entity_counter = 0
        self._relation_counter = 0

        # Files
        self.entities_file = self.memory_dir / "semantic_entities.json"
        self.relations_file = self.memory_dir / "semantic_relations.json"

        # Load from disk
        self.load_from_disk()

    def _init_default_ontology(self):
        """Initialize default domain ontology"""
        # Character hierarchy
        self._add_ontology_node("character", None)
        self._add_ontology_node("protagonist", "character")
        self._add_ontology_node("antagonist", "character")
        self._add_ontology_node("supporting", "character")

        # Location hierarchy
        self._add_ontology_node("location", None)
        self._add_ontology_node("indoor", "location")
        self._add_ontology_node("outdoor", "location")
        self._add_ontology_node("building", "indoor")
        self._add_ontology_node("room", "building")

        # Object hierarchy
        self._add_ontology_node("object", None)
        self._add_ontology_node("weapon", "object")
        self._add_ontology_node("artifact", "object")
        self._add_ontology_node("document", "object")

        # Concept hierarchy
        self._add_ontology_node("concept", None)
        self._add_ontology_node("theme", "concept")
        self._add_ontology_node("rule", "concept")
        self._add_ontology_node("event_type", "concept")

    def _add_ontology_node(self, concept: str, parent: Optional[str]):
        """Add a node to the ontology"""
        node = OntologyNode(concept=concept, parent=parent)
        self._ontology[concept] = node

        if parent and parent in self._ontology:
            self._ontology[parent].children.append(concept)

    def _generate_entity_id(self) -> str:
        """Generate unique entity ID"""
        self._entity_counter += 1
        return f"ent_{self._entity_counter:05d}"

    def _generate_relation_id(self) -> str:
        """Generate unique relation ID"""
        self._relation_counter += 1
        return f"rel_{self._relation_counter:05d}"

    def add_entity(
        self,
        name: str,
        entity_type: str,
        attributes: Dict[str, Any] = None,
        chapter: int = None,
        aliases: List[str] = None,
        metadata: Dict = None
    ) -> Entity:
        """
        Add a new entity to semantic memory

        Args:
            name: Entity name
            entity_type: Type (character, location, object, concept)
            attributes: Entity attributes
            chapter: Chapter where entity was introduced
            aliases: Alternative names
            metadata: Additional metadata

        Returns:
            Entity: The created entity
        """
        # Check if entity already exists
        if name in self._entity_by_name:
            # Update existing entity
            entity_id = self._entity_by_name[name]
            entity = self._entities[entity_id]
            if attributes:
                entity.attributes.update(attributes)
            if chapter:
                entity.last_updated_chapter = chapter
            return entity

        # Create new entity
        entity_id = self._generate_entity_id()
        entity = Entity(
            id=entity_id,
            name=name,
            entity_type=entity_type,
            attributes=attributes or {},
            created_chapter=chapter or self._current_chapter,
            last_updated_chapter=chapter or self._current_chapter,
            aliases=aliases or [],
            metadata=metadata or {}
        )

        # Store entity
        self._entities[entity_id] = entity
        self._entity_by_name[name] = entity_id

        # Store aliases
        for alias in (aliases or []):
            self._entity_by_name[alias] = entity_id

        # Save
        self.save_to_disk()

        return entity

    def add_relation(
        self,
        source_name: str,
        relation_type: str,
        target_name: str,
        properties: Dict[str, Any] = None,
        chapter: int = None,
        confidence: float = 1.0,
        create_entities: bool = True
    ) -> Optional[Relation]:
        """
        Add a relationship between entities

        Args:
            source_name: Source entity name
            relation_type: Type of relationship
            target_name: Target entity name
            properties: Relationship properties
            chapter: Chapter where relation was established
            confidence: Confidence in this relationship
            create_entities: Create entities if they don't exist

        Returns:
            Relation: The created relation, or None if failed
        """
        # Get or create entities
        source_id = self._entity_by_name.get(source_name)
        target_id = self._entity_by_name.get(target_name)

        if create_entities:
            if not source_id:
                source_entity = self.add_entity(source_name, "character", chapter=chapter)
                source_id = source_entity.id
            if not target_id:
                target_entity = self.add_entity(target_name, "character", chapter=chapter)
                target_id = target_entity.id

        if not source_id or not target_id:
            return None

        # Check if relation already exists
        for rel_id in self._outgoing.get(source_id, []):
            rel = self._relations[rel_id]
            if rel.target_id == target_id and rel.relation_type == relation_type:
                # Update existing relation
                if properties:
                    rel.properties.update(properties)
                if chapter:
                    rel.last_updated_chapter = chapter
                return rel

        # Create new relation
        relation_id = self._generate_relation_id()
        relation = Relation(
            id=relation_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            properties=properties or {},
            established_chapter=chapter or self._current_chapter,
            last_updated_chapter=chapter or self._current_chapter,
            confidence=confidence
        )

        # Store relation
        self._relations[relation_id] = relation
        self._outgoing[source_id].append(relation_id)
        self._incoming[target_id].append(relation_id)
        self._relations_by_type[relation_type].append(relation_id)

        # Save
        self.save_to_disk()

        return relation

    def get_entity(self, name: str) -> Optional[Entity]:
        """Get entity by name"""
        entity_id = self._entity_by_name.get(name)
        if entity_id:
            return self._entities.get(entity_id)
        return None

    def get_entity_by_id(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID"""
        return self._entities.get(entity_id)

    def get_relations(
        self,
        entity_name: str = None,
        relation_type: str = None,
        direction: str = "both"
    ) -> List[Relation]:
        """
        Get relations

        Args:
            entity_name: Filter by entity (optional)
            relation_type: Filter by relation type (optional)
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of matching relations
        """
        results = []

        if entity_name:
            entity_id = self._entity_by_name.get(entity_name)
            if not entity_id:
                return []

            if direction in ("outgoing", "both"):
                for rel_id in self._outgoing.get(entity_id, []):
                    results.append(self._relations[rel_id])

            if direction in ("incoming", "both"):
                for rel_id in self._incoming.get(entity_id, []):
                    results.append(self._relations[rel_id])
        else:
            results = list(self._relations.values())

        # Filter by type
        if relation_type:
            results = [r for r in results if r.relation_type == relation_type]

        return results

    def get_related_entities(
        self,
        entity_name: str,
        relation_type: str = None,
        max_depth: int = 1
    ) -> List[Tuple[Entity, str, int]]:
        """
        Get entities related to this one

        Args:
            entity_name: Starting entity
            relation_type: Filter by relation type (optional)
            max_depth: Maximum traversal depth

        Returns:
            List of (entity, relation_type, distance) tuples
        """
        entity_id = self._entity_by_name.get(entity_name)
        if not entity_id:
            return []

        visited = {entity_id}
        results = []
        queue = [(entity_id, 0)]  # (entity_id, distance)

        while queue:
            current_id, distance = queue.pop(0)

            if distance >= max_depth:
                continue

            # Get outgoing relations
            for rel_id in self._outgoing.get(current_id, []):
                rel = self._relations.get(rel_id)
                if rel is None:
                    # 防御性处理：跳过可能残留的悬挂 rel_id
                    continue

                if relation_type and rel.relation_type != relation_type:
                    continue

                target_id = rel.target_id
                if target_id not in visited:
                    visited.add(target_id)
                    target_entity = self._entities.get(target_id)
                    if target_entity:
                        results.append((target_entity, rel.relation_type, distance + 1))
                        queue.append((target_id, distance + 1))

            # Get incoming relations
            for rel_id in self._incoming.get(current_id, []):
                rel = self._relations.get(rel_id)
                if rel is None:
                    # 防御性处理：跳过可能残留的悬挂 rel_id
                    continue

                if relation_type and rel.relation_type != relation_type:
                    continue

                source_id = rel.source_id
                if source_id not in visited:
                    visited.add(source_id)
                    source_entity = self._entities.get(source_id)
                    if source_entity:
                        results.append((source_entity, rel.relation_type, distance + 1))
                        queue.append((source_id, distance + 1))

        return results

    def infer_relations(self) -> List[Relation]:
        """
        Infer implicit relationships

        Returns:
            List of inferred relations
        """
        inferred = []

        # Inverse relations
        for rel in list(self._relations.values()):
            inverse_type = self.DEFAULT_RELATION_INVERSES.get(rel.relation_type)
            if inverse_type and inverse_type != rel.relation_type:
                # Check if inverse already exists
                inverse_exists = any(
                    r.relation_type == inverse_type and
                    r.source_id == rel.target_id and
                    r.target_id == rel.source_id
                    for r_id in self._outgoing.get(rel.target_id, [])
                    for r in [self._relations[r_id]]
                )

                if not inverse_exists:
                    # Create inverse relation with lower confidence
                    inv_relation = self.add_relation(
                        source_name=self._entities[rel.target_id].name,
                        relation_type=inverse_type,
                        target_name=self._entities[rel.source_id].name,
                        chapter=rel.established_chapter,
                        confidence=rel.confidence * 0.9
                    )
                    if inv_relation:
                        inferred.append(inv_relation)

        # Transitive relations
        for trans_type in self.TRANSITIVE_RELATIONS:
            # Find chains: A -> B -> C
            # 用 list(...) 快照，因为下方 add_relation 会改写 self._relations /
            # self._outgoing，直接迭代会触发 "dictionary changed size during iteration"。
            for rel_ab in list(self._relations.values()):
                if rel_ab.relation_type != trans_type:
                    continue

                for rel_bc_id in list(self._outgoing.get(rel_ab.target_id, [])):
                    rel_bc = self._relations.get(rel_bc_id)
                    if rel_bc is None:
                        continue
                    if rel_bc.relation_type != trans_type:
                        continue

                    # Check if A -> C already exists
                    ac_exists = any(
                        r.relation_type == trans_type and
                        r.target_id == rel_bc.target_id
                        for r_id in self._outgoing.get(rel_ab.source_id, [])
                        for r in [self._relations[r_id]]
                    )

                    if not ac_exists:
                        # Infer A -> C
                        ac_relation = self.add_relation(
                            source_name=self._entities[rel_ab.source_id].name,
                            relation_type=trans_type,
                            target_name=self._entities[rel_bc.target_id].name,
                            chapter=max(rel_ab.established_chapter, rel_bc.established_chapter),
                            confidence=min(rel_ab.confidence, rel_bc.confidence) * 0.8
                        )
                        if ac_relation:
                            inferred.append(ac_relation)

        return inferred

    def check_consistency(self, assertion: Dict) -> Tuple[bool, List[str]]:
        """
        Check if an assertion is consistent with known facts

        Args:
            assertion: Dict with 'subject', 'predicate', 'object'

        Returns:
            Tuple of (is_consistent, list_of_conflicts)
        """
        conflicts = []

        subject_name = assertion.get("subject")
        predicate = assertion.get("predicate")
        obj = assertion.get("object")

        if not subject_name or not predicate:
            return (True, [])

        subject = self.get_entity(subject_name)
        if not subject:
            return (True, [])  # Unknown entity, no conflict

        # Check attribute consistency
        if predicate.startswith("is_") or predicate.startswith("has_"):
            existing = subject.attributes.get(predicate)
            if existing is not None and existing != obj:
                conflicts.append(
                    f"{subject_name}.{predicate} = {existing}, but assertion says {obj}"
                )

        # Check relationship consistency
        relation_conflicts = {
            "friend_of": ["enemy_of"],
            "enemy_of": ["friend_of"],
            "married_to": ["lover_of"],  # Could be same person, but suspicious
        }

        if predicate in relation_conflicts:
            for conflict_type in relation_conflicts[predicate]:
                conflicting = self.get_relations(
                    entity_name=subject_name,
                    relation_type=conflict_type
                )
                for rel in conflicting:
                    if rel.target_id == self._entity_by_name.get(obj):
                        conflicts.append(
                            f"{subject_name} is {predicate} {obj}, "
                            f"but also {conflict_type} {obj}"
                        )

        return (len(conflicts) == 0, conflicts)

    def update_entity(
        self,
        name: str,
        attributes: Dict[str, Any] = None,
        chapter: int = None
    ) -> Optional[Entity]:
        """Update entity attributes"""
        entity = self.get_entity(name)
        if not entity:
            return None

        if attributes:
            entity.attributes.update(attributes)

        if chapter:
            entity.last_updated_chapter = chapter
            self._current_chapter = max(self._current_chapter, chapter)

        self.save_to_disk()
        return entity

    def remove_entity(self, name: str) -> bool:
        """Remove entity and its relations"""
        entity_id = self._entity_by_name.get(name)
        if not entity_id:
            return False

        # Remove relations。注意要同时清理"对端"实体的邻接表，
        # 否则邻居的 _incoming/_outgoing 仍残留指向已删除关系的 rel_id，
        # 之后 get_related_entities 访问 self._relations[rel_id] 会 KeyError。
        rel_ids = set(self._outgoing.get(entity_id, [])) | set(self._incoming.get(entity_id, []))
        for rel_id in rel_ids:
            rel = self._relations.pop(rel_id, None)
            if not rel:
                continue
            type_bucket = self._relations_by_type.get(rel.relation_type)
            if type_bucket and rel_id in type_bucket:
                type_bucket.remove(rel_id)
            # 从两个端点的邻接表移除该 rel_id
            if rel.source_id in self._outgoing and rel_id in self._outgoing[rel.source_id]:
                self._outgoing[rel.source_id].remove(rel_id)
            if rel.target_id in self._incoming and rel_id in self._incoming[rel.target_id]:
                self._incoming[rel.target_id].remove(rel_id)

        # Remove entity
        entity = self._entities.pop(entity_id)
        del self._entity_by_name[name]
        for alias in entity.aliases:
            self._entity_by_name.pop(alias, None)

        # Clean up indices
        self._outgoing.pop(entity_id, None)
        self._incoming.pop(entity_id, None)

        self.save_to_disk()
        return True

    def clear(self):
        """Clear all semantic memory"""
        self._entities.clear()
        self._entity_by_name.clear()
        self._relations.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._relations_by_type.clear()
        self._entity_counter = 0
        self._relation_counter = 0
        self.save_to_disk()

    def save_to_disk(self):
        """Save semantic memory to disk"""
        try:
            # Save entities
            entities_data = {
                "entities": [e.to_dict() for e in self._entities.values()],
                "entity_counter": self._entity_counter,
                "current_chapter": self._current_chapter
            }
            with open(self.entities_file, 'w', encoding='utf-8') as f:
                json.dump(entities_data, f, ensure_ascii=False, indent=2)

            # Save relations
            relations_data = {
                "relations": [r.to_dict() for r in self._relations.values()],
                "relation_counter": self._relation_counter
            }
            with open(self.relations_file, 'w', encoding='utf-8') as f:
                json.dump(relations_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"保存语义记忆失败: {e}")

    def load_from_disk(self):
        """Load semantic memory from disk"""
        # Load entities
        if self.entities_file.exists():
            try:
                with open(self.entities_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for entity_data in data.get("entities", []):
                    entity = Entity.from_dict(entity_data)
                    self._entities[entity.id] = entity
                    self._entity_by_name[entity.name] = entity.id
                    for alias in entity.aliases:
                        self._entity_by_name[alias] = entity.id

                self._entity_counter = data.get("entity_counter", 0)
                self._current_chapter = data.get("current_chapter", 1)

            except Exception as e:
                print(f"加载实体失败: {e}")

        # Load relations
        if self.relations_file.exists():
            try:
                with open(self.relations_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for rel_data in data.get("relations", []):
                    relation = Relation.from_dict(rel_data)
                    self._relations[relation.id] = relation
                    self._outgoing[relation.source_id].append(relation.id)
                    self._incoming[relation.target_id].append(relation.id)
                    self._relations_by_type[relation.relation_type].append(relation.id)

                self._relation_counter = data.get("relation_counter", 0)

            except Exception as e:
                print(f"加载关系失败: {e}")

    def to_text_description(self, entity_types: List[str] = None) -> str:
        """Convert to text description for prompts"""
        parts = ["[语义记忆 - 世界知识]:"]

        # Group by type
        by_type: Dict[str, List[Entity]] = defaultdict(list)
        for entity in self._entities.values():
            by_type[entity.entity_type].append(entity)

        # Display by type
        type_names = {
            "character": "人物",
            "location": "地点",
            "object": "物品",
            "concept": "概念"
        }

        for entity_type in (entity_types or ["character", "location"]):
            if entity_type not in by_type:
                continue

            type_name = type_names.get(entity_type, entity_type)
            parts.append(f"\n{type_name}:")

            for entity in by_type[entity_type][:10]:  # Limit to 10 per type
                # Basic info
                info = f"- {entity.name}"

                # Key attributes
                key_attrs = []
                for key in ["age", "gender", "role", "occupation", "personality"]:
                    if key in entity.attributes:
                        key_attrs.append(f"{key}={entity.attributes[key]}")
                if key_attrs:
                    info += f" ({', '.join(key_attrs)})"

                # Relationships
                relations = self.get_relations(entity.name)
                if relations:
                    rel_summary = []
                    for rel in relations[:3]:
                        target = self._entities.get(rel.target_id)
                        if target:
                            rel_summary.append(f"{rel.relation_type}→{target.name}")
                    if rel_summary:
                        info += f" [{', '.join(rel_summary)}]"

                parts.append(info)

        return "\n".join(parts)

    def get_stats(self) -> Dict:
        """Get statistics about semantic memory"""
        return {
            "entity_count": len(self._entities),
            "relation_count": len(self._relations),
            "entity_types": {
                t: len([e for e in self._entities.values() if e.entity_type == t])
                for t in ["character", "location", "object", "concept"]
            },
            "relation_types": {
                t: len(ids) for t, ids in self._relations_by_type.items()
            },
            "current_chapter": self._current_chapter
        }


# Test
if __name__ == "__main__":
    sm = SemanticMemory()

    # Add entities
    lm = sm.add_entity("李明", "character", {"age": 25, "gender": "男"})
    wf = sm.add_entity("王芳", "character", {"age": 23, "gender": "女"})
    lib = sm.add_entity("图书馆", "location", {"type": "公共"})

    # Add relations
    sm.add_relation("李明", "friend_of", "王芳")
    sm.add_relation("李明", "located_at", "图书馆")
    sm.add_relation("王芳", "located_at", "图书馆")

    # Test queries
    print("Entities related to 李明:")
    for entity, rel_type, dist in sm.get_related_entities("李明"):
        print(f"  - {entity.name} ({rel_type}, distance={dist})")

    print("\nConsistency check:")
    is_consistent, conflicts = sm.check_consistency({
        "subject": "李明",
        "predicate": "enemy_of",
        "object": "王芳"
    })
    print(f"  enemy_of relation: consistent={is_consistent}, conflicts={conflicts}")

    print("\nStats:")
    print(sm.get_stats())

    print("\nText description:")
    print(sm.to_text_description())
