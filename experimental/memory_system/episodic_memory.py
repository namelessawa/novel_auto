#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Episodic Memory Module
Story events with temporal embeddings, scene-level indexing, and importance scoring

Inspired by cognitive science episodic memory:
- Events are stored with temporal context
- Importance determines retention and retrieval priority
- Time decay affects retrieval relevance
- Scene-level granularity for precise access

Key Features:
1. Temporal Embeddings - Events are indexed by time (chapter position)
2. Importance Scoring - Plot relevance, character impact, foreshadowing potential
3. Time-Aware Retrieval - Recent events weighted higher
4. Scene-Level Indexing - Granular access to story segments
"""

import json
import time
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
import math


@dataclass
class Episode:
    """
    A single episode (story event) in episodic memory

    Episodes are granular story events with:
    - Temporal position (chapter, scene, timestamp)
    - Importance scoring (multiple dimensions)
    - Entity associations
    - Foreshadowing links
    """
    id: str
    chapter_num: int
    scene_num: int
    title: str
    content: str
    summary: str

    # Temporal information
    timestamp: float = field(default_factory=time.time)
    story_time: Optional[str] = None  # e.g., "第三天傍晚"

    # Importance dimensions (0.0 - 1.0)
    plot_relevance: float = 0.5  # How central to main plot
    character_impact: float = 0.5  # How much it affects characters
    emotional_weight: float = 0.5  # Emotional significance
    foreshadowing_potential: float = 0.0  # Could be referenced later

    # Entities
    characters: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    key_objects: List[str] = field(default_factory=list)

    # Relationships
    causes: List[str] = field(default_factory=list)  # IDs of causing episodes
    results: List[str] = field(default_factory=list)  # IDs of resulting episodes
    foreshadows: List[str] = field(default_factory=list)  # IDs of foreshadowed episodes

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def importance_score(self) -> float:
        """Calculate overall importance score"""
        weights = {
            'plot': 0.35,
            'character': 0.25,
            'emotional': 0.20,
            'foreshadowing': 0.20
        }
        return (
            self.plot_relevance * weights['plot'] +
            self.character_impact * weights['character'] +
            self.emotional_weight * weights['emotional'] +
            self.foreshadowing_potential * weights['foreshadowing']
        )

    @property
    def token_estimate(self) -> int:
        """Estimate token count"""
        return len(self.content) // 2

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "chapter_num": self.chapter_num,
            "scene_num": self.scene_num,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "story_time": self.story_time,
            "plot_relevance": self.plot_relevance,
            "character_impact": self.character_impact,
            "emotional_weight": self.emotional_weight,
            "foreshadowing_potential": self.foreshadowing_potential,
            "characters": self.characters,
            "locations": self.locations,
            "key_objects": self.key_objects,
            "causes": self.causes,
            "results": self.results,
            "foreshadows": self.foreshadows,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Episode':
        return cls(
            id=data["id"],
            chapter_num=data["chapter_num"],
            scene_num=data["scene_num"],
            title=data["title"],
            content=data["content"],
            summary=data["summary"],
            timestamp=data.get("timestamp", time.time()),
            story_time=data.get("story_time"),
            plot_relevance=data.get("plot_relevance", 0.5),
            character_impact=data.get("character_impact", 0.5),
            emotional_weight=data.get("emotional_weight", 0.5),
            foreshadowing_potential=data.get("foreshadowing_potential", 0.0),
            characters=data.get("characters", []),
            locations=data.get("locations", []),
            key_objects=data.get("key_objects", []),
            causes=data.get("causes", []),
            results=data.get("results", []),
            foreshadows=data.get("foreshadows", []),
            metadata=data.get("metadata", {})
        )


class EpisodicMemory:
    """
    Episodic Memory with temporal embeddings and importance scoring

    Features:
    - Scene-level granular indexing
    - Importance-weighted storage
    - Time-aware retrieval with decay
    - Cause-effect relationship tracking
    - Foreshadowing management

    Capacity: ~50K tokens (configurable)
    TTL: Hours (story session based)
    """

    DEFAULT_CAPACITY = 50000  # tokens
    TIME_DECAY_RATE = 0.1  # Importance decay per chapter distance

    def __init__(
        self,
        memory_dir: str = "memory_system",
        capacity: int = DEFAULT_CAPACITY
    ):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.capacity = capacity

        # Episodes storage
        self._episodes: Dict[str, Episode] = {}
        self._episodes_by_chapter: Dict[int, List[str]] = {}  # chapter -> episode IDs
        self._episodes_by_entity: Dict[str, List[str]] = {}  # entity -> episode IDs

        # Scene counter per chapter
        self._scene_counters: Dict[int, int] = {}

        # ID counter
        self._id_counter = 0

        # Current chapter (for time decay)
        self._current_chapter = 0

        # Files
        self.episodes_file = self.memory_dir / "episodic_memory.json"

        # Embedding service for semantic retrieval
        self._embedding_service = None
        self._vector_index: Dict[str, List[float]] = {}  # episode_id -> embedding

        # Load from disk
        self.load_from_disk()

    def _generate_id(self, chapter: int, scene: int) -> str:
        """Generate unique episode ID"""
        return f"ep_{chapter:03d}_{scene:03d}"

    def _get_embedding_service(self):
        """Get embedding service (lazy load)"""
        if self._embedding_service is None:
            try:
                from core.embedding_service import EmbeddingService
                self._embedding_service = EmbeddingService(
                    model_name="BAAI/bge-small-zh-v1.5"
                )
            except ImportError:
                print("Warning: EmbeddingService not available, using keyword matching")
        return self._embedding_service

    def add_episode(
        self,
        chapter_num: int,
        title: str,
        content: str,
        summary: str = None,
        characters: List[str] = None,
        locations: List[str] = None,
        key_objects: List[str] = None,
        plot_relevance: float = 0.5,
        character_impact: float = 0.5,
        emotional_weight: float = 0.5,
        foreshadowing_potential: float = 0.0,
        story_time: str = None,
        causes: List[str] = None,
        metadata: Dict = None
    ) -> Episode:
        """
        Add a new episode to episodic memory

        Args:
            chapter_num: Chapter number
            title: Episode title
            content: Episode content
            summary: Episode summary (auto-generated if None)
            characters: Characters involved
            locations: Locations involved
            key_objects: Important objects
            plot_relevance: Plot importance (0-1)
            character_impact: Character impact (0-1)
            emotional_weight: Emotional significance (0-1)
            foreshadowing_potential: Foreshadowing potential (0-1)
            story_time: Story-internal time
            causes: IDs of causing episodes
            metadata: Additional metadata

        Returns:
            Episode: The created episode
        """
        # Get scene number
        if chapter_num not in self._scene_counters:
            self._scene_counters[chapter_num] = 0
        self._scene_counters[chapter_num] += 1
        scene_num = self._scene_counters[chapter_num]

        # Generate ID
        episode_id = self._generate_id(chapter_num, scene_num)

        # Auto-generate summary if needed
        if summary is None:
            summary = self._extract_summary(content)

        # Create episode
        episode = Episode(
            id=episode_id,
            chapter_num=chapter_num,
            scene_num=scene_num,
            title=title,
            content=content,
            summary=summary,
            story_time=story_time,
            plot_relevance=plot_relevance,
            character_impact=character_impact,
            emotional_weight=emotional_weight,
            foreshadowing_potential=foreshadowing_potential,
            characters=characters or [],
            locations=locations or [],
            key_objects=key_objects or [],
            causes=causes or [],
            metadata=metadata or {}
        )

        # Store episode
        self._episodes[episode_id] = episode

        # Update chapter index
        if chapter_num not in self._episodes_by_chapter:
            self._episodes_by_chapter[chapter_num] = []
        self._episodes_by_chapter[chapter_num].append(episode_id)

        # Update entity indices
        for entity in (characters or []):
            if entity not in self._episodes_by_entity:
                self._episodes_by_entity[entity] = []
            self._episodes_by_entity[entity].append(episode_id)

        for entity in (locations or []):
            if entity not in self._episodes_by_entity:
                self._episodes_by_entity[entity] = []
            self._episodes_by_entity[entity].append(episode_id)

        # Generate embedding
        self._index_episode(episode)

        # Update current chapter
        self._current_chapter = max(self._current_chapter, chapter_num)

        # Save to disk
        self.save_to_disk()

        return episode

    def _extract_summary(self, content: str, max_length: int = 150) -> str:
        """Extract summary from content"""
        if len(content) <= max_length:
            return content

        # Truncate at sentence boundary
        truncated = content[:max_length]
        for end in ['。', '！', '？', '.', '!', '?']:
            pos = truncated.rfind(end)
            if pos > max_length // 2:
                return truncated[:pos + 1]

        return truncated + "..."

    def _index_episode(self, episode: Episode):
        """Create vector index for episode"""
        embedding_service = self._get_embedding_service()
        if embedding_service is None:
            return

        try:
            # Create text for embedding
            text = f"{episode.summary} {' '.join(episode.characters)} {' '.join(episode.locations)}"
            embedding = embedding_service.embed_text(text)
            self._vector_index[episode.id] = embedding.tolist()
        except Exception as e:
            print(f"Failed to index episode: {e}")

    def retrieve(
        self,
        query: str = None,
        entities: List[str] = None,
        chapter_range: Tuple[int, int] = None,
        top_k: int = 5,
        time_decay: float = TIME_DECAY_RATE,
        min_importance: float = 0.0
    ) -> List[Episode]:
        """
        Retrieve episodes with time decay and importance weighting

        Args:
            query: Natural language query
            entities: Filter by entities
            chapter_range: Filter by chapter range (min, max)
            top_k: Number of episodes to return
            time_decay: Decay rate per chapter distance
            min_importance: Minimum importance threshold

        Returns:
            List of episodes, sorted by relevance
        """
        candidates = list(self._episodes.values())

        # Filter by entities
        if entities:
            entity_set = set(entities)
            candidates = [
                ep for ep in candidates
                if entity_set & (set(ep.characters) | set(ep.locations))
            ]

        # Filter by chapter range
        if chapter_range:
            min_ch, max_ch = chapter_range
            candidates = [
                ep for ep in candidates
                if min_ch <= ep.chapter_num <= max_ch
            ]

        # Filter by importance
        if min_importance > 0:
            candidates = [
                ep for ep in candidates
                if ep.importance_score >= min_importance
            ]

        # Score episodes
        scored = []
        for ep in candidates:
            score = self._calculate_retrieval_score(ep, query, time_decay)
            scored.append((score, ep))

        # Sort and return top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for score, ep in scored[:top_k]]

    def _calculate_retrieval_score(
        self,
        episode: Episode,
        query: str,
        time_decay: float
    ) -> float:
        """
        Calculate retrieval score for an episode

        Score = semantic_similarity * importance * time_decay_factor
        """
        # Time decay factor
        chapter_distance = self._current_chapter - episode.chapter_num
        decay_factor = math.exp(-time_decay * chapter_distance)

        # Importance factor
        importance = episode.importance_score

        # Semantic similarity (if query provided)
        semantic_score = 1.0
        if query and episode.id in self._vector_index:
            embedding_service = self._get_embedding_service()
            if embedding_service:
                try:
                    query_embedding = embedding_service.embed_text(query)
                    # Cosine similarity
                    ep_embedding = self._vector_index[episode.id]
                    semantic_score = self._cosine_similarity(query_embedding.tolist(), ep_embedding)
                except Exception:
                    pass

        return semantic_score * importance * decay_factor

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x ** 2 for x in a))
        norm_b = math.sqrt(sum(y ** 2 for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def get_by_chapter(self, chapter_num: int) -> List[Episode]:
        """Get all episodes from a chapter"""
        episode_ids = self._episodes_by_chapter.get(chapter_num, [])
        return [self._episodes[eid] for eid in episode_ids if eid in self._episodes]

    def get_by_entity(self, entity: str, top_k: int = 10) -> List[Episode]:
        """Get episodes involving an entity"""
        episode_ids = self._episodes_by_entity.get(entity, [])
        episodes = [self._episodes[eid] for eid in episode_ids if eid in self._episodes]

        # Sort by importance
        episodes.sort(key=lambda x: x.importance_score, reverse=True)
        return episodes[:top_k]

    def get_cause_effect_chain(self, episode_id: str) -> Dict:
        """
        Get cause-effect chain for an episode

        Returns:
            Dict with 'causes' and 'effects' lists
        """
        episode = self._episodes.get(episode_id)
        if not episode:
            return {"causes": [], "effects": []}

        causes = []
        for cause_id in episode.causes:
            if cause_id in self._episodes:
                causes.append(self._episodes[cause_id])

        effects = []
        for ep in self._episodes.values():
            if episode_id in ep.causes:
                effects.append(ep)

        return {"causes": causes, "effects": effects}

    def get_foreshadowing_candidates(self) -> List[Episode]:
        """Get episodes with high foreshadowing potential that haven't been resolved"""
        return [
            ep for ep in self._episodes.values()
            if ep.foreshadowing_potential > 0.5 and not ep.foreshadows
        ]

    def link_foreshadowing(self, setup_id: str, payoff_id: str):
        """Link two episodes as foreshadowing setup and payoff"""
        if setup_id in self._episodes and payoff_id in self._episodes:
            self._episodes[setup_id].foreshadows.append(payoff_id)
            self.save_to_disk()

    def clear(self):
        """Clear all episodes"""
        self._episodes.clear()
        self._episodes_by_chapter.clear()
        self._episodes_by_entity.clear()
        self._scene_counters.clear()
        self._vector_index.clear()
        self._id_counter = 0
        self.save_to_disk()

    def save_to_disk(self):
        """Save episodic memory to disk"""
        try:
            data = {
                "episodes": [ep.to_dict() for ep in self._episodes.values()],
                "scene_counters": self._scene_counters,
                "current_chapter": self._current_chapter,
                "id_counter": self._id_counter,
                "last_saved": datetime.now().isoformat()
            }

            with open(self.episodes_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"保存情节记忆失败: {e}")

    def load_from_disk(self):
        """Load episodic memory from disk"""
        if not self.episodes_file.exists():
            return

        try:
            with open(self.episodes_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Restore episodes
            for ep_data in data.get("episodes", []):
                episode = Episode.from_dict(ep_data)
                self._episodes[episode.id] = episode

                # Rebuild indices
                if episode.chapter_num not in self._episodes_by_chapter:
                    self._episodes_by_chapter[episode.chapter_num] = []
                self._episodes_by_chapter[episode.chapter_num].append(episode.id)

                for entity in episode.characters + episode.locations:
                    if entity not in self._episodes_by_entity:
                        self._episodes_by_entity[entity] = []
                    self._episodes_by_entity[entity].append(episode.id)

                # Rebuild vector index
                self._index_episode(episode)

            # Restore counters
            self._scene_counters = data.get("scene_counters", {})
            self._current_chapter = data.get("current_chapter", 0)
            self._id_counter = data.get("id_counter", 0)

        except Exception as e:
            print(f"加载情节记忆失败: {e}")

    def to_text_description(self, max_episodes: int = 10) -> str:
        """Convert to text description for prompts"""
        parts = ["[情节记忆 - 重要事件]:"]

        # Get recent important episodes
        recent = self.retrieve(top_k=max_episodes, time_decay=0.05)

        for ep in recent:
            time_info = f"第{ep.chapter_num}章"
            if ep.story_time:
                time_info += f" ({ep.story_time})"

            importance_marker = "★" if ep.importance_score > 0.7 else ""
            parts.append(f"- {time_info} {importance_marker}: {ep.summary}")

            if ep.characters:
                parts.append(f"  角色: {', '.join(ep.characters[:3])}")

        return "\n".join(parts)

    def get_stats(self) -> Dict:
        """Get statistics about episodic memory"""
        return {
            "episode_count": len(self._episodes),
            "chapter_count": len(self._episodes_by_chapter),
            "entity_count": len(self._episodes_by_entity),
            "total_tokens": sum(ep.token_estimate for ep in self._episodes.values()),
            "avg_importance": sum(ep.importance_score for ep in self._episodes.values()) / len(self._episodes) if self._episodes else 0,
            "current_chapter": self._current_chapter
        }


# Test
if __name__ == "__main__":
    em = EpisodicMemory()

    # Add some episodes
    ep1 = em.add_episode(
        chapter_num=1,
        title="相遇",
        content="李明在图书馆第一次遇到了王芳，两人因为一本书而相识。",
        characters=["李明", "王芳"],
        locations=["图书馆"],
        plot_relevance=0.8,
        character_impact=0.9,
        foreshadowing_potential=0.6
    )

    ep2 = em.add_episode(
        chapter_num=2,
        title="争执",
        content="李明和王芳因为观点不同发生了争执，但最后和好了。",
        characters=["李明", "王芳"],
        plot_relevance=0.6,
        character_impact=0.7,
        causes=[ep1.id]
    )

    print("Episodes by chapter 1:")
    for ep in em.get_by_chapter(1):
        print(f"  - {ep.title}: {ep.summary}")

    print("\nEpisodes by entity '李明':")
    for ep in em.get_by_entity("李明"):
        print(f"  - {ep.title}")

    print("\nCause-effect chain for ep2:")
    chain = em.get_cause_effect_chain(ep2.id)
    print(f"  Causes: {[ep.title for ep in chain['causes']]}")

    print("\nStats:")
    print(em.get_stats())
