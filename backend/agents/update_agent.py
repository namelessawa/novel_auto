"""Update Agent — parses generated text and synchronizes world state."""

from __future__ import annotations

import json
import logging

from nf_core.llm_client import llm_client
from memory_system.models import Entity, EntityType, Relation, RelationType, Section
from graph.knowledge_graph import KnowledgeGraph
from memory.summary_tree import SummaryTree
from vector.vector_store import VectorStore

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是一位精确的文本分析师。请从给定的小说正文中提取世界状态变更。

输出 JSON 格式（严格 JSON，不要加 markdown 代码块标记）：
{
  "summary": "50字以内的本节摘要",
  "new_entities": [
    {"id": "entity_id", "name": "显示名", "type": "character|location|item|skill|faction", "attributes": {}}
  ],
  "updated_entities": [
    {"id": "entity_id", "attribute_updates": {"key": "value"}}
  ],
  "removed_entities": ["entity_id"],
  "new_relations": [
    {"source": "id1", "target": "id2", "type": "located_at|holds|knows|hostile|allied|loves|parent_of|member_of|master_of|custom", "label": "描述"}
  ],
  "removed_relations": [
    {"source": "id1", "target": "id2"}
  ],
  "scene": {
    "environment": "当前环境描述",
    "active_characters": [{"entity_id": "id", "name": "名字", "emotion": "情绪"}]
  }
}

注意：
- entity_id 使用小写字母和下划线。
- 只提取明确发生的变更，不要臆测。
- 角色死亡用 attribute_updates: {"status": "dead"} 表示。
"""


class UpdateAgent:
    def __init__(
        self,
        graph: KnowledgeGraph,
        vector_store: VectorStore,
        summary_tree: SummaryTree,
    ) -> None:
        self._graph = graph
        self._vector_store = vector_store
        self._summary_tree = summary_tree

    async def update(self, section: Section) -> dict:
        """Parse generated text and sync world state. Never raises."""
        # Step 1: Call LLM to extract changes (non-critical, can fail)
        changes = await self._extract_changes(section)

        # Step 2: Apply graph changes (best-effort)
        self._apply_graph_changes(changes)

        # Step 3: Archive to vector store (best-effort)
        summary = changes.get("summary", section.title)
        archived_section = Section(
            chapter=section.chapter,
            section=section.section,
            title=section.title,
            content=section.content,
            summary=summary,
            word_count=section.word_count,
        )
        await self._vector_store.add_section(archived_section)

        # Step 4: Update summary tree (local, no LLM call on first sections)
        try:
            await self._summary_tree.add_section_summary(
                section.chapter, section.section, summary
            )
        except Exception as e:
            logger.error("Summary tree update failed: %s", e)

        return changes

    async def _extract_changes(self, section: Section) -> dict:
        """Call LLM to extract world state changes. Returns fallback on error."""
        try:
            resp = await llm_client.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=f"请分析以下正文的世界状态变更：\n\n{section.content}",
                temperature=0.1,
                max_tokens=40960,
                agent_id="update_agent",
                priority="medium",
            )
        except Exception as e:
            logger.error("UpdateAgent LLM call failed: %s", e)
            return {"summary": section.content[:50], "scene": {}}

        changes = self._parse_json(resp.content)
        logger.info(
            "UpdateAgent parsed: %d new entities, %d new relations, summary=%s",
            len(changes.get("new_entities", [])),
            len(changes.get("new_relations", [])),
            changes.get("summary", "")[:30],
        )
        return changes

    def _apply_graph_changes(self, changes: dict) -> None:
        """Apply entity/relation changes to the knowledge graph. Best-effort."""
        for e in changes.get("new_entities", []):
            try:
                self._graph.add_entity(
                    Entity(
                        id=e["id"],
                        name=e["name"],
                        entity_type=EntityType(e.get("type", "character")),
                        attributes=e.get("attributes", {}),
                    )
                )
            except (KeyError, ValueError) as err:
                logger.warning("Skipping invalid entity: %s", err)

        for e in changes.get("updated_entities", []):
            try:
                self._graph.update_entity_attributes(
                    e["id"], e.get("attribute_updates", {})
                )
            except (KeyError, ValueError):
                pass

        for eid in changes.get("removed_entities", []):
            self._graph.remove_entity(eid)

        for r in changes.get("new_relations", []):
            try:
                self._graph.add_relation(
                    Relation(
                        source_id=r["source"],
                        target_id=r["target"],
                        relation_type=RelationType(r.get("type", "custom")),
                        label=r.get("label", ""),
                    )
                )
            except (KeyError, ValueError) as err:
                logger.warning("Skipping invalid relation: %s", err)

        for r in changes.get("removed_relations", []):
            try:
                self._graph.remove_relation(r["source"], r["target"])
            except (KeyError, ValueError):
                pass

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"summary": text[:50], "scene": {}}
