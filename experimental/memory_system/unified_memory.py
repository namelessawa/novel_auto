#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Memory System
Integrates all four memory layers (Working, Episodic, Semantic, Procedural)

This module provides a unified interface for the cognitive science-inspired
multi-layered memory architecture:

1. Working Memory - Short-term active context with TTL
2. Episodic Memory - Story events with temporal embeddings
3. Semantic Memory - Knowledge graph of entities and relationships
4. Procedural Memory - Style patterns and narrative techniques

The layers work together:
- Working Memory provides immediate context for generation
- Episodic Memory retrieves relevant past events
- Semantic Memory maintains world consistency
- Procedural Memory guides writing style and techniques
"""

from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from .working_memory import WorkingMemory
from .episodic_memory import EpisodicMemory, Episode
from .semantic_memory import SemanticMemory, Entity, Relation
from .procedural_memory import ProceduralMemory, StyleProfile, NarrativeTechnique


class UnifiedMemorySystem:
    """
    Unified Multi-Layered Memory System

    Features:
    - Four-layer cognitive architecture
    - Cross-layer queries and updates
    - Automatic memory consolidation
    - Unified context building for LLM
    """

    def __init__(self, memory_dir: str = "memory_system"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Initialize all layers
        self.working = WorkingMemory(memory_dir=memory_dir)
        self.episodic = EpisodicMemory(memory_dir=memory_dir)
        self.semantic = SemanticMemory(memory_dir=memory_dir)
        self.procedural = ProceduralMemory(memory_dir=memory_dir)

        # Current chapter for updates
        self._current_chapter = 1

    def update_chapter(self, chapter: int):
        """Update current chapter for all layers"""
        self._current_chapter = chapter
        self.episodic._current_chapter = chapter
        self.semantic._current_chapter = chapter

    def add_scene(
        self,
        chapter_num: int,
        scene_num: int,
        title: str,
        content: str,
        summary: str = None,
        characters: List[str] = None,
        locations: List[str] = None,
        importance: float = 0.5
    ):
        """
        Add a scene to memory (updates multiple layers)

        Args:
            chapter_num: Chapter number
            scene_num: Scene number
            title: Scene title
            content: Scene content
            summary: Scene summary
            characters: Characters in scene
            locations: Locations in scene
            importance: Overall importance (0-1)
        """
        # 1. Update Working Memory (immediate context)
        self.working.add_context(
            content=content,
            item_type="scene",
            entities=characters,
            importance=importance
        )

        # 2. Update Episodic Memory (story events)
        self.episodic.add_episode(
            chapter_num=chapter_num,
            title=title,
            content=content,
            summary=summary,
            characters=characters,
            locations=locations,
            plot_relevance=importance,
            character_impact=importance
        )

        # 3. Update Semantic Memory (entities and relations)
        for char in (characters or []):
            self.semantic.add_entity(
                name=char,
                entity_type="character",
                chapter=chapter_num
            )

        for loc in (locations or []):
            self.semantic.add_entity(
                name=loc,
                entity_type="location",
                chapter=chapter_num
            )

        # Update character locations in semantic memory
        for char in (characters or []):
            for loc in (locations or []):
                self.semantic.add_relation(
                    source_name=char,
                    relation_type="located_at",
                    target_name=loc,
                    chapter=chapter_num,
                    create_entities=False
                )

    def add_dialogue(
        self,
        speaker: str,
        dialogue: str,
        listener: str = None,
        emotion: str = None,
        context: str = None
    ):
        """
        Add dialogue to memory

        Args:
            speaker: Who is speaking
            dialogue: What they say
            listener: Who they're speaking to
            emotion: Emotional tone
            context: Surrounding context
        """
        # Update Working Memory
        entities = [speaker]
        if listener:
            entities.append(listener)

        self.working.add_context(
            content=f"「{dialogue}」",
            item_type="dialogue",
            entities=entities,
            metadata={"speaker": speaker, "listener": listener, "emotion": emotion}
        )

        # Update Semantic Memory
        self.semantic.add_entity(speaker, "character")
        if listener:
            self.semantic.add_entity(listener, "character")
            # Record interaction
            self.semantic.add_relation(
                source_name=speaker,
                relation_type="talks_to",
                target_name=listener,
                chapter=self._current_chapter
            )

    def add_character_development(
        self,
        character: str,
        attribute: str,
        value: Any,
        chapter: int = None
    ):
        """
        Record character development

        Args:
            character: Character name
            attribute: Attribute being developed
            value: New value or development
            chapter: Chapter where this happens
        """
        chapter = chapter or self._current_chapter

        # Update Semantic Memory
        self.semantic.update_entity(
            name=character,
            attributes={attribute: value},
            chapter=chapter
        )

        # Refresh working memory attention
        if character in self.working._entity_attention:
            self.working._entity_attention[character].refresh()

    def add_relationship(
        self,
        character1: str,
        relationship_type: str,
        character2: str,
        chapter: int = None,
        properties: Dict = None
    ):
        """
        Add/update relationship between characters

        Args:
            character1: First character
            relationship_type: Type of relationship
            character2: Second character
            chapter: Chapter where relationship is established/changed
            properties: Additional properties
        """
        chapter = chapter or self._current_chapter

        # Update Semantic Memory
        self.semantic.add_relation(
            source_name=character1,
            relation_type=relationship_type,
            target_name=character2,
            chapter=chapter,
            properties=properties
        )

    def get_full_context(
        self,
        query: str = None,
        max_tokens: int = 4000,
        include_working: bool = True,
        include_episodic: bool = True,
        include_semantic: bool = True,
        include_procedural: bool = True
    ) -> str:
        """
        Get full memory context for LLM generation

        Args:
            query: Optional query for targeted retrieval
            max_tokens: Maximum total tokens
            include_working: Include working memory
            include_episodic: Include episodic memory
            include_semantic: Include semantic memory
            include_procedural: Include procedural memory

        Returns:
            Formatted context string
        """
        parts = []
        remaining_tokens = max_tokens

        # 精确 token 计数（带降级）：旧实现用 len(context)//2 估算 token，
        # 对中文（约 1 字符 ≈ 1+ token）严重低估，导致 remaining_tokens 消耗过慢、
        # 最终上下文可能远超 max_tokens。
        try:
            from utils.token_counter import TokenCounter
            _counter = TokenCounter()

            def _count(text: str) -> int:
                return _counter.count_tokens(text)

            def _truncate(text: str, n: int) -> str:
                return _counter.truncate_to_tokens(text, n)
        except Exception:
            def _count(text: str) -> int:
                return len(text)

            def _truncate(text: str, n: int) -> str:
                return text[:n]

        # Priority order: Working > Semantic > Episodic > Procedural
        priorities = [
            (include_working, self.working, 0.35),      # 35% of tokens
            (include_semantic, self.semantic, 0.25),    # 25% of tokens
            (include_episodic, self.episodic, 0.30),    # 30% of tokens
            (include_procedural, self.procedural, 0.10) # 10% of tokens
        ]

        for should_include, memory_layer, ratio in priorities:
            if not should_include:
                continue

            layer_tokens = int(max_tokens * ratio)
            if remaining_tokens < layer_tokens * 0.5:
                # Not enough tokens left, skip
                continue

            # Get context from layer
            if hasattr(memory_layer, 'get_context'):
                context = memory_layer.get_context(max_tokens=layer_tokens)
            else:
                # 该层没有 token 感知的 get_context，手动按本层预算截断，
                # 否则 to_text_description() 会忽略 layer_tokens 无限输出。
                context = _truncate(memory_layer.to_text_description(), layer_tokens)

            if context:
                parts.append(context)
                remaining_tokens -= _count(context)  # 精确 token 计数

        return "\n\n".join(parts)

    def query_relevant_memories(
        self,
        query: str,
        entities: List[str] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Query all memory layers for relevant information

        Args:
            query: Query string
            entities: Relevant entities
            top_k: Number of results per layer

        Returns:
            Dict with results from each layer
        """
        results = {
            "working": {},
            "episodic": [],
            "semantic": {},
            "procedural": []
        }

        # Working Memory: Active entities
        if entities:
            active = self.working.get_active_entities()
            results["working"]["active_entities"] = [e for e in active if e in (entities or [])]

        # Episodic Memory: Relevant events
        results["episodic"] = self.episodic.retrieve(
            query=query,
            entities=entities,
            top_k=top_k
        )

        # Semantic Memory: Entity info and relationships
        if entities:
            for entity in entities[:3]:  # Limit to avoid too much detail
                entity_obj = self.semantic.get_entity(entity)
                if entity_obj:
                    relations = self.semantic.get_related_entities(entity)
                    results["semantic"][entity] = {
                        "attributes": entity_obj.attributes,
                        "relations": [(e.name, r) for e, r, _ in relations[:5]]
                    }

        # Procedural Memory: Suggested techniques
        results["procedural"] = self.procedural.suggest_technique({
            "genre": query,  # Simplified
        })

        return results

    def check_consistency(self, assertion: Dict) -> Tuple[bool, List[str]]:
        """
        Check if an assertion is consistent with memory

        Args:
            assertion: Dict with 'subject', 'predicate', 'object'

        Returns:
            Tuple of (is_consistent, conflicts)
        """
        return self.semantic.check_consistency(assertion)

    def get_character_state(self, name: str) -> Dict:
        """
        Get full state of a character across memory layers

        Args:
            name: Character name

        Returns:
            Dict with state from all layers
        """
        state = {
            "name": name,
            "working": {},
            "episodic": [],
            "semantic": {},
            "attention": 0.0
        }

        # Working Memory: Current attention
        if name in self.working._entity_attention:
            state["working"]["attention_score"] = self.working._entity_attention[name].attention_score
            state["working"]["mention_count"] = self.working._entity_attention[name].mention_count
            state["attention"] = self.working._entity_attention[name].attention_score

        # Episodic Memory: Recent events
        state["episodic"] = self.episodic.get_by_entity(name, top_k=5)

        # Semantic Memory: Attributes and relationships
        entity = self.semantic.get_entity(name)
        if entity:
            state["semantic"]["attributes"] = entity.attributes
            state["semantic"]["relations"] = [
                (e.name, r, d)
                for e, r, d in self.semantic.get_related_entities(name)
            ]

        return state

    def consolidate(self):
        """
        Consolidate memory (transfer important items between layers)

        This implements the memory consolidation process:
        - Important working memory items → Episodic memory
        - Frequent episodic events → Semantic memory
        - Effective patterns → Procedural memory
        """
        # Find important working memory items
        for item in list(self.working._items.values()):
            if item.importance > 0.8 and item.item_type == "scene":
                # Transfer to episodic memory if not already there
                pass  # Already handled in add_scene

        # Infer implicit relationships in semantic memory
        inferred = self.semantic.infer_relations()
        if inferred:
            print(f"Inferred {len(inferred)} new relationships")

    def set_style(self, style_name: str) -> bool:
        """Set the current writing style"""
        return self.procedural.set_current_style(style_name)

    def analyze_and_learn(self, text: str, genre: str = None):
        """
        Analyze text and learn patterns

        Args:
            text: Text to analyze
            genre: Optional genre tag
        """
        # Analyze style
        profile = self.procedural.analyze_style(text)

        # Extract patterns
        pattern = self.procedural.extract_pattern(
            text,
            context={"genres": [genre] if genre else []}
        )

        return {
            "style_profile": profile,
            "extracted_pattern": pattern
        }

    def save_all(self):
        """Save all memory layers to disk"""
        self.working.save_to_disk()
        self.episodic.save_to_disk()
        self.semantic.save_to_disk()
        self.procedural.save_to_disk()

    def load_all(self):
        """Load all memory layers from disk"""
        self.working.load_from_disk()
        self.episodic.load_from_disk()
        self.semantic.load_from_disk()
        self.procedural.load_from_disk()

    def clear_all(self):
        """Clear all memory layers"""
        self.working.clear()
        self.episodic.clear()
        self.semantic.clear()
        self.procedural.clear()

    def get_stats(self) -> Dict:
        """Get statistics for all layers"""
        return {
            "working": self.working.get_stats(),
            "episodic": self.episodic.get_stats(),
            "semantic": self.semantic.get_stats(),
            "procedural": self.procedural.get_stats(),
            "current_chapter": self._current_chapter
        }

    def to_prompt_context(self, max_tokens: int = 3000) -> str:
        """
        Convert to optimized prompt context for LLM

        This creates a context string optimized for LLM consumption:
        - Prioritized information
        - Token-efficient formatting
        - Clear structure

        Args:
            max_tokens: Maximum tokens

        Returns:
            Formatted context string
        """
        parts = []

        # 1. Current focus and active entities (Working)
        focus = self.working.get_focus()
        if focus:
            parts.append(f"[当前焦点]: {focus[0]} ({focus[1]})")

        active_entities = self.working.get_active_entities()
        if active_entities:
            parts.append(f"[活跃角色]: {', '.join(active_entities[:5])}")

        # 2. Key entity states (Semantic)
        semantic_context = self.semantic.to_text_description(["character", "location"])
        parts.append(semantic_context)

        # 3. Recent important events (Episodic)
        episodic_context = self.episodic.to_text_description(max_episodes=5)
        parts.append(episodic_context)

        # 4. Style guidance (Procedural)
        current_style = self.procedural.get_current_style()
        if current_style:
            parts.append(self.procedural.get_style_guidance(current_style.name))

        return "\n\n".join(parts)


# Backward compatibility adapter
class MemorySystemAdapter:
    """
    Adapter to provide backward compatibility with old memory system interface
    while using the new unified system internally
    """

    def __init__(self, memory_dir: str = "memory_system"):
        self.unified = UnifiedMemorySystem(memory_dir=memory_dir)

        # Keep old-style attributes for compatibility
        self.sliding_window = self.unified.working
        self.entity_state = self.unified.semantic
        self.long_term_memory = self.unified.episodic
        self.hierarchical_summary = None  # Will be handled separately

    def add_chapter(
        self,
        chapter_num: int,
        title: str,
        content: str,
        entities: List[str] = None
    ):
        """Add chapter to memory (compatibility method)"""
        self.unified.add_scene(
            chapter_num=chapter_num,
            scene_num=1,
            title=title,
            content=content,
            characters=entities
        )

    def get_context(self) -> str:
        """Get context for generation (compatibility method)"""
        return self.unified.get_full_context()

    def clear(self):
        """Clear memory (compatibility method)"""
        self.unified.clear_all()

    def save_to_disk(self):
        """Save to disk (compatibility method)"""
        self.unified.save_all()

    def load_from_disk(self):
        """Load from disk (compatibility method)"""
        self.unified.load_all()


# Test
if __name__ == "__main__":
    ums = UnifiedMemorySystem(memory_dir="test_memory")

    # Add some content
    ums.add_scene(
        chapter_num=1,
        scene_num=1,
        title="初次相遇",
        content="李明在图书馆第一次见到了王芳，两人因为一本书而相识。",
        characters=["李明", "王芳"],
        locations=["图书馆"],
        importance=0.8
    )

    ums.add_dialogue(
        speaker="李明",
        dialogue="你好，这本书很有趣。",
        listener="王芳"
    )

    # Query
    print("Character state for 李明:")
    state = ums.get_character_state("李明")
    print(f"  Attention: {state['attention']}")
    print(f"  Episodes: {len(state['episodic'])}")
    print()

    # Get full context
    print("Full context:")
    print(ums.get_full_context(max_tokens=500))
    print()

    # Stats
    print("Stats:")
    print(ums.get_stats())
