"""Retrieval Agent — gathers entity states and historical context for generation."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models import ActionPlan
from graph.knowledge_graph import KnowledgeGraph
from vector.vector_store import VectorStore


@dataclass(frozen=True)
class RetrievalContext:
    entity_states: list[str] = field(default_factory=list)
    historical_fragments: list[str] = field(default_factory=list)


class RetrievalAgent:
    def __init__(
        self, graph: KnowledgeGraph, vector_store: VectorStore
    ) -> None:
        self._graph = graph
        self._vector_store = vector_store

    async def retrieve(self, plan: ActionPlan) -> RetrievalContext:
        # 1. Query knowledge graph for key entities
        entity_states: list[str] = []
        for eid in plan.key_entities:
            state = self._graph.get_entity_state_summary(eid)
            entity_states.append(state)

        # 2. Semantic search for historical details using keywords + plan text
        query_text = plan.plan_text + " " + " ".join(plan.keywords)
        docs = await self._vector_store.query(query_text)
        historical_fragments = [
            f"[第{d['metadata'].get('chapter', '?')}章] {d['content'][:300]}"
            for d in docs
        ]

        return RetrievalContext(
            entity_states=entity_states,
            historical_fragments=historical_fragments,
        )
