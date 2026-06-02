"""Tests for the Knowledge Graph module."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from graph.knowledge_graph import KnowledgeGraph
from memory_system.models import Entity, EntityType, Relation, RelationType


def test_add_and_get_entity():
    kg = KnowledgeGraph()
    entity = Entity(id="hero", name="主角", entity_type=EntityType.CHARACTER, attributes={"level": 1})
    kg.add_entity(entity)

    result = kg.get_entity("hero")
    assert result is not None
    assert result.name == "主角"
    assert result.attributes["level"] == 1


def test_update_attributes():
    kg = KnowledgeGraph()
    kg.add_entity(Entity(id="hero", name="主角", entity_type=EntityType.CHARACTER, attributes={"level": 1}))
    kg.update_entity_attributes("hero", {"level": 5, "hp": 100})

    result = kg.get_entity("hero")
    assert result.attributes["level"] == 5
    assert result.attributes["hp"] == 100


def test_add_relation_and_query():
    kg = KnowledgeGraph()
    kg.add_entity(Entity(id="hero", name="主角", entity_type=EntityType.CHARACTER))
    kg.add_entity(Entity(id="sword", name="神剑", entity_type=EntityType.ITEM))

    kg.add_relation(Relation(
        source_id="hero", target_id="sword",
        relation_type=RelationType.HOLDS, label="持有神剑"
    ))

    assert kg.has_relation("hero", "sword", RelationType.HOLDS)
    assert not kg.has_relation("hero", "sword", RelationType.HOSTILE)


def test_reachability():
    kg = KnowledgeGraph()
    kg.add_entity(Entity(id="a", name="A", entity_type=EntityType.CHARACTER))
    kg.add_entity(Entity(id="b", name="B", entity_type=EntityType.CHARACTER))
    kg.add_entity(Entity(id="c", name="C", entity_type=EntityType.CHARACTER))

    kg.add_relation(Relation(source_id="a", target_id="b", relation_type=RelationType.KNOWS))
    kg.add_relation(Relation(source_id="b", target_id="c", relation_type=RelationType.KNOWS))

    assert kg.is_reachable("a", "c")
    assert not kg.is_reachable("c", "a")


def test_remove_entity():
    kg = KnowledgeGraph()
    kg.add_entity(Entity(id="hero", name="主角", entity_type=EntityType.CHARACTER))
    kg.remove_entity("hero")
    assert kg.get_entity("hero") is None


def test_list_entities_by_type():
    kg = KnowledgeGraph()
    kg.add_entity(Entity(id="hero", name="主角", entity_type=EntityType.CHARACTER))
    kg.add_entity(Entity(id="town", name="小镇", entity_type=EntityType.LOCATION))

    chars = kg.list_entities(EntityType.CHARACTER)
    assert len(chars) == 1
    assert chars[0].id == "hero"


def test_snapshot_and_rollback():
    kg = KnowledgeGraph()
    kg.add_entity(Entity(id="hero", name="主角", entity_type=EntityType.CHARACTER, attributes={"level": 1}))
    sid = kg.take_snapshot(1)

    # Modify state
    kg.update_entity_attributes("hero", {"level": 10})
    kg.add_entity(Entity(id="villain", name="反派", entity_type=EntityType.CHARACTER))

    assert kg.get_entity("hero").attributes["level"] == 10
    assert kg.get_entity("villain") is not None

    # Rollback
    kg.rollback(sid)
    assert kg.get_entity("hero").attributes["level"] == 1
    assert kg.get_entity("villain") is None
