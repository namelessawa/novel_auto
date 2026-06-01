"""
Knowledge Graph — NetworkX 有向图，跟踪实体 / 关系，带快照与回滚。

设计目标：作为现有 ``character_relationship.py`` 的升级版本，可由
``NovelGenerator`` 通过 ``use_knowledge_graph=True`` flag 选择启用。
快照与回滚机制借鉴 novel_frame，便于在多章节生成中做"状态保护"。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import networkx as nx

from .models import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relation,
    RelationType,
)


class KnowledgeGraph:
    """Thin wrapper around NetworkX DiGraph 用于小说世界状态跟踪。"""

    def __init__(self, memory_dir: str, *, snapshot_subdir: str = "snapshots") -> None:
        """
        Args:
            memory_dir: 小说数据目录 (如 ``results/{novel_id}``)
            snapshot_subdir: 快照子目录，默认 ``snapshots``
        """
        self._graph = nx.DiGraph()
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self._snapshot_dir = self.memory_dir / snapshot_subdir
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self.memory_dir / "knowledge_graph.json"

    # -- entity CRUD ----------------------------------------------------------

    def add_entity(self, entity: Entity) -> None:
        self._graph.add_node(
            entity.id,
            name=entity.name,
            entity_type=entity.entity_type.value,
            attributes=dict(entity.attributes),
        )

    def update_entity_attributes(self, entity_id: str, updates: dict) -> None:
        if entity_id not in self._graph:
            raise KeyError(f"Entity {entity_id} not found")
        attrs = dict(self._graph.nodes[entity_id].get("attributes", {}))
        attrs.update(updates)
        self._graph.nodes[entity_id]["attributes"] = attrs

    def remove_entity(self, entity_id: str) -> None:
        if entity_id in self._graph:
            self._graph.remove_node(entity_id)

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        if entity_id not in self._graph:
            return None
        data = self._graph.nodes[entity_id]
        return Entity(
            id=entity_id,
            name=data["name"],
            entity_type=EntityType(data["entity_type"]),
            attributes=dict(data.get("attributes", {})),
        )

    def list_entities(self, entity_type: Optional[EntityType] = None) -> list[Entity]:
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
                    attributes=dict(data.get("attributes", {})),
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
            attributes=dict(relation.attributes),
        )

    def remove_relation(self, source_id: str, target_id: str) -> None:
        if self._graph.has_edge(source_id, target_id):
            self._graph.remove_edge(source_id, target_id)

    def get_relations(self, entity_id: str) -> list[Relation]:
        relations: list[Relation] = []
        if entity_id not in self._graph:
            return relations
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
        relation_type: Optional[RelationType] = None,
    ) -> bool:
        if not self._graph.has_edge(source_id, target_id):
            return False
        if relation_type is None:
            return True
        data = self._graph.edges[source_id, target_id]
        return data.get("relation_type") == relation_type.value

    def is_reachable(self, source_id: str, target_id: str) -> bool:
        if source_id not in self._graph or target_id not in self._graph:
            return False
        return nx.has_path(self._graph, source_id, target_id)

    def get_entity_state_summary(self, entity_id: str) -> str:
        entity = self.get_entity(entity_id)
        if not entity:
            return f"实体 {entity_id} 不存在。"
        lines = [
            f"【{entity.name}】类型={entity.entity_type.value}",
            f"  属性: {json.dumps(entity.attributes, ensure_ascii=False)}",
        ]
        for r in self.get_relations(entity_id):
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
        path = self._snapshot_dir / f"{snapshot_id}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(self._snapshot_to_dict(snapshot), f, ensure_ascii=False, indent=2)
        return snapshot_id

    def rollback(self, snapshot_id: str) -> None:
        path = self._snapshot_dir / f"{snapshot_id}.json"
        with path.open("r", encoding="utf-8") as f:
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
        if not self._snapshot_dir.is_dir():
            return []
        return sorted(
            [f.stem for f in self._snapshot_dir.iterdir() if f.suffix == ".json"],
            reverse=True,
        )

    # -- persistence (live state, not snapshot) ------------------------------

    def save_to_disk(self) -> None:
        """把当前图持久化到 ``memory_dir/knowledge_graph.json``。"""
        data = self.to_dict(include_attributes=True)
        with self._state_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_disk(self) -> None:
        """从 ``memory_dir/knowledge_graph.json`` 恢复（若文件不存在则忽略）。"""
        if not self._state_path.is_file():
            return
        with self._state_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self._graph.clear()
        for e in data.get("entities", []):
            self.add_entity(
                Entity(
                    id=e["id"],
                    name=e["name"],
                    entity_type=EntityType(e.get("type", e.get("entity_type", "character"))),
                    attributes=e.get("attributes", {}),
                )
            )
        for r in data.get("relations", []):
            self.add_relation(
                Relation(
                    source_id=r["source"] if "source" in r else r["source_id"],
                    target_id=r["target"] if "target" in r else r["target_id"],
                    relation_type=RelationType(r.get("relation_type", "custom")),
                    label=r.get("label", ""),
                    weight=r.get("weight", 1.0),
                    attributes=r.get("attributes", {}),
                )
            )

    def clear(self) -> None:
        self._graph.clear()
        if self._state_path.exists():
            self._state_path.unlink()

    # -- serialization --------------------------------------------------------

    def to_dict(self, *, include_attributes: bool = False) -> dict:
        entities = []
        for e in self.list_entities():
            item = {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type.value,
            }
            if include_attributes:
                item["attributes"] = e.attributes
            entities.append(item)
        edges = []
        for src, tgt, data in self._graph.edges(data=True):
            item = {
                "source": src,
                "target": tgt,
                "relation_type": data.get("relation_type", ""),
                "label": data.get("label", ""),
            }
            if include_attributes:
                item["weight"] = data.get("weight", 1.0)
                item["attributes"] = data.get("attributes", {})
            edges.append(item)
        return {"entities": entities, "relations": edges}

    def to_text_description(self) -> str:
        """供 LLM prompt 上下文使用的简短文字描述。"""
        if self._graph.number_of_nodes() == 0:
            return "（知识图谱为空）"
        lines = [f"实体数: {self._graph.number_of_nodes()} | 关系数: {self._graph.number_of_edges()}"]
        for e in self.list_entities()[:10]:  # 限制 10 个，避免 prompt 过长
            lines.append(f"  {e.name} ({e.entity_type.value})")
        if self._graph.number_of_nodes() > 10:
            lines.append(f"  ... 共 {self._graph.number_of_nodes()} 个实体")
        return "\n".join(lines)

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _edge_to_relation(src: str, tgt: str, data: dict) -> Relation:
        return Relation(
            source_id=src,
            target_id=tgt,
            relation_type=RelationType(data.get("relation_type", "custom")),
            label=data.get("label", ""),
            weight=data.get("weight", 1.0),
            attributes=dict(data.get("attributes", {})),
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


__all__ = ["KnowledgeGraph"]
