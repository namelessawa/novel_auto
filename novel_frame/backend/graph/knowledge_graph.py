"""Knowledge Graph — directed graph of entities and relations with snapshot support."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import networkx as nx

from config.settings import settings
from memory_system.models import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relation,
    RelationType,
)


class KnowledgeGraph:
    """Thin wrapper around NetworkX DiGraph for novel world-state tracking."""

    def __init__(self, snapshot_dir: str | None = None) -> None:
        self._graph = nx.DiGraph()
        self._snapshot_dir = snapshot_dir or settings.graph_snapshot_dir
        os.makedirs(self._snapshot_dir, exist_ok=True)

    # -- entity CRUD ----------------------------------------------------------

    def add_entity(self, entity: Entity) -> None:
        self._graph.add_node(
            entity.id,
            name=entity.name,
            entity_type=entity.entity_type.value,
            attributes=entity.attributes,
        )

    def update_entity_attributes(
        self, entity_id: str, updates: dict
    ) -> None:
        if entity_id not in self._graph:
            raise KeyError(f"Entity {entity_id} not found")
        attrs = dict(self._graph.nodes[entity_id].get("attributes", {}))
        attrs.update(updates)
        self._graph.nodes[entity_id]["attributes"] = attrs

    def remove_entity(self, entity_id: str) -> None:
        if entity_id in self._graph:
            self._graph.remove_node(entity_id)

    def get_entity(self, entity_id: str) -> Entity | None:
        if entity_id not in self._graph:
            return None
        data = self._graph.nodes[entity_id]
        return Entity(
            id=entity_id,
            name=data["name"],
            entity_type=EntityType(data["entity_type"]),
            attributes=data.get("attributes", {}),
        )

    def list_entities(
        self, entity_type: EntityType | None = None
    ) -> list[Entity]:
        results: list[Entity] = []
        for nid, data in self._graph.nodes(data=True):
            if "name" not in data or "entity_type" not in data:
                continue
            if entity_type and data.get("entity_type") != entity_type.value:
                continue
            results.append(
                Entity(
                    id=nid,
                    name=data["name"],
                    entity_type=EntityType(data["entity_type"]),
                    attributes=data.get("attributes", {}),
                )
            )
        return results

    # -- relation CRUD --------------------------------------------------------

    def add_relation(self, relation: Relation) -> None:
        self._graph.add_edge(
            relation.source_id,
            relation.target_id,
            relation_type=relation.relation_type.value,
            label=relation.label,
            weight=relation.weight,
            attributes=relation.attributes,
        )

    def remove_relation(self, source_id: str, target_id: str) -> None:
        if self._graph.has_edge(source_id, target_id):
            self._graph.remove_edge(source_id, target_id)

    def get_relations(self, entity_id: str) -> list[Relation]:
        relations: list[Relation] = []
        for _, target, data in self._graph.out_edges(entity_id, data=True):
            relations.append(self._edge_to_relation(entity_id, target, data))
        for source, _, data in self._graph.in_edges(entity_id, data=True):
            relations.append(self._edge_to_relation(source, entity_id, data))
        return relations

    # -- queries --------------------------------------------------------------

    def has_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType | None = None,
    ) -> bool:
        if not self._graph.has_edge(source_id, target_id):
            return False
        if relation_type is None:
            return True
        data = self._graph.edges[source_id, target_id]
        return data.get("relation_type") == relation_type.value

    def is_reachable(self, source_id: str, target_id: str) -> bool:
        return nx.has_path(self._graph, source_id, target_id)

    def get_entity_state_summary(self, entity_id: str) -> str:
        entity = self.get_entity(entity_id)
        if not entity:
            return f"实体 {entity_id} 不存在。"
        relations = self.get_relations(entity_id)
        lines = [
            f"【{entity.name}】类型={entity.entity_type.value}",
            f"  属性: {json.dumps(entity.attributes, ensure_ascii=False)}",
        ]
        for r in relations:
            lines.append(
                f"  关系: {r.source_id} --[{r.relation_type.value}: {r.label}]--> {r.target_id}"
            )
        return "\n".join(lines)

    # -- snapshot / rollback --------------------------------------------------

    def take_snapshot(self, chapter: int) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        snapshot_id = f"snapshot_ch{chapter}_{ts}"
        entities = self.list_entities()
        relations: list[Relation] = []
        for src, tgt, data in self._graph.edges(data=True):
            relations.append(self._edge_to_relation(src, tgt, data))

        snapshot = GraphSnapshot(
            snapshot_id=snapshot_id,
            chapter=chapter,
            timestamp=ts,
            entities=entities,
            relations=relations,
        )
        path = os.path.join(self._snapshot_dir, f"{snapshot_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._snapshot_to_dict(snapshot), f, ensure_ascii=False, indent=2)
        return snapshot_id

    def rollback(self, snapshot_id: str) -> None:
        path = os.path.join(self._snapshot_dir, f"{snapshot_id}.json")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._graph.clear()
        for e in data["entities"]:
            self.add_entity(
                Entity(
                    id=e["id"],
                    name=e["name"],
                    entity_type=EntityType(e["entity_type"]),
                    attributes=e.get("attributes", {}),
                )
            )
        for r in data["relations"]:
            self.add_relation(
                Relation(
                    source_id=r["source_id"],
                    target_id=r["target_id"],
                    relation_type=RelationType(r["relation_type"]),
                    label=r.get("label", ""),
                    weight=r.get("weight", 1.0),
                    attributes=r.get("attributes", {}),
                )
            )

    def list_snapshots(self) -> list[str]:
        files = os.listdir(self._snapshot_dir)
        return sorted(
            [f.replace(".json", "") for f in files if f.endswith(".json")],
            reverse=True,
        )

    def to_dict(self) -> dict:
        entities = [
            {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type.value,
                "attributes": e.attributes,
            }
            for e in self.list_entities()
        ]
        edges = []
        for src, tgt, data in self._graph.edges(data=True):
            edges.append({
                "source": src,
                "target": tgt,
                "relation_type": data.get("relation_type", ""),
                "label": data.get("label", ""),
            })
        return {"entities": entities, "relations": edges}

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _edge_to_relation(src: str, tgt: str, data: dict) -> Relation:
        return Relation(
            source_id=src,
            target_id=tgt,
            relation_type=RelationType(data.get("relation_type", "custom")),
            label=data.get("label", ""),
            weight=data.get("weight", 1.0),
            attributes=data.get("attributes", {}),
        )

    @staticmethod
    def _snapshot_to_dict(snap: GraphSnapshot) -> dict:
        return {
            "snapshot_id": snap.snapshot_id,
            "chapter": snap.chapter,
            "timestamp": snap.timestamp,
            "entities": [
                {
                    "id": e.id,
                    "name": e.name,
                    "entity_type": e.entity_type.value,
                    "attributes": e.attributes,
                }
                for e in snap.entities
            ],
            "relations": [
                {
                    "source_id": r.source_id,
                    "target_id": r.target_id,
                    "relation_type": r.relation_type.value,
                    "label": r.label,
                    "weight": r.weight,
                    "attributes": r.attributes,
                }
                for r in snap.relations
            ],
        }
