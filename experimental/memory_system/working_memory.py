#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Working Memory Module
Short-term active context with TTL-based decay
Inspired by cognitive science working memory model

This module maintains the immediate context for generation:
- Active scene context (last 500-1000 tokens)
- Current dialogue/narrative focus
- Real-time entity tracking with attention mechanism
- TTL-based automatic decay
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from collections import OrderedDict
import json
from pathlib import Path
from datetime import datetime


@dataclass
class ContextItem:
    """A single item in working memory"""
    id: str
    content: str
    item_type: str  # "scene", "dialogue", "narrative", "entity_mention"
    timestamp: float
    ttl_seconds: float
    importance: float = 1.0  # 0.0 - 1.0
    entities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if item has exceeded TTL"""
        return time.time() - self.timestamp > self.ttl_seconds

    @property
    def token_estimate(self) -> int:
        """Estimate token count (roughly 2 chars per Chinese token)"""
        return len(self.content) // 2

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "item_type": self.item_type,
            "timestamp": self.timestamp,
            "ttl_seconds": self.ttl_seconds,
            "importance": self.importance,
            "entities": self.entities,
            "metadata": self.metadata
        }


@dataclass
class EntityAttention:
    """Tracks attention level for entities in working memory"""
    name: str
    attention_score: float = 1.0  # Decays over time
    last_mention_time: float = field(default_factory=time.time)
    mention_count: int = 1
    context_items: Set[str] = field(default_factory=set)  # IDs of context items

    def update_attention(self, decay_rate: float = 0.9):
        """Apply time-based attention decay"""
        time_since_mention = time.time() - self.last_mention_time
        # Exponential decay: attention halves every 60 seconds
        self.attention_score *= decay_rate ** (time_since_mention / 60)

    def refresh(self):
        """Refresh attention on new mention"""
        self.attention_score = min(1.0, self.attention_score + 0.5)
        self.last_mention_time = time.time()
        self.mention_count += 1


class WorkingMemory:
    """
    Working Memory with TTL and Attention Mechanism

    This module maintains immediate context for generation:
    - Active scene context (last N tokens)
    - Current dialogue/narrative focus
    - Real-time entity tracking with attention
    - TTL-based automatic decay

    Capacity: ~1000 tokens (configurable)
    TTL: 5 minutes (configurable)
    """

    DEFAULT_CAPACITY = 1000  # tokens
    DEFAULT_TTL = 300  # seconds (5 minutes)
    MAX_ITEMS = 50  # Maximum number of items

    def __init__(
        self,
        memory_dir: str = "memory_system",
        capacity: int = DEFAULT_CAPACITY,
        default_ttl: float = DEFAULT_TTL
    ):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.capacity = capacity
        self.default_ttl = default_ttl

        # Ordered dict for LRU-like behavior
        self._items: OrderedDict[str, ContextItem] = OrderedDict()

        # Entity attention tracking
        self._entity_attention: Dict[str, EntityAttention] = {}

        # Current focus (what the narrative is centered on)
        self._current_focus: Optional[str] = None
        self._focus_type: Optional[str] = None  # "character", "location", "plot"

        # Counter for generating IDs
        self._id_counter = 0

        # File for persistence
        self.state_file = self.memory_dir / "working_memory.json"

        # Load from disk
        self.load_from_disk()

    def add_context(
        self,
        content: str,
        item_type: str,
        entities: List[str] = None,
        importance: float = 1.0,
        ttl_seconds: float = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Add a new context item to working memory

        Args:
            content: The text content
            item_type: Type of context ("scene", "dialogue", "narrative", "entity_mention")
            entities: List of entities mentioned
            importance: Importance weight (0.0 - 1.0)
            ttl_seconds: Time-to-live (uses default if None)
            metadata: Additional metadata

        Returns:
            str: ID of the added item
        """
        # Generate ID
        item_id = f"ctx_{self._id_counter}"
        self._id_counter += 1

        # Create item
        item = ContextItem(
            id=item_id,
            content=content,
            item_type=item_type,
            timestamp=time.time(),
            ttl_seconds=ttl_seconds or self.default_ttl,
            importance=importance,
            entities=entities or [],
            metadata=metadata or {}
        )

        # Add to items
        self._items[item_id] = item

        # Update entity attention
        for entity in (entities or []):
            self._update_entity_attention(entity, item_id)

        # Enforce capacity limits
        self._enforce_capacity()

        # Save to disk
        self.save_to_disk()

        return item_id

    def _update_entity_attention(self, entity: str, item_id: str):
        """Update or create entity attention tracking"""
        if entity in self._entity_attention:
            self._entity_attention[entity].refresh()
            self._entity_attention[entity].context_items.add(item_id)
        else:
            attention = EntityAttention(name=entity)
            attention.context_items.add(item_id)
            self._entity_attention[entity] = attention

    def _enforce_capacity(self):
        """Enforce capacity limits by removing low-priority items"""
        # First, remove expired items
        self._decay_expired()

        # Calculate current token usage
        total_tokens = sum(item.token_estimate for item in self._items.values())

        # If over capacity, remove lowest importance items
        while total_tokens > self.capacity and len(self._items) > 1:
            # Find lowest importance item
            lowest_id = min(
                self._items.keys(),
                key=lambda x: self._items[x].importance
            )

            # Remove it
            removed = self._items.pop(lowest_id)
            total_tokens -= removed.token_estimate

            # Clean up entity attention references
            for entity in removed.entities:
                if entity in self._entity_attention:
                    self._entity_attention[entity].context_items.discard(lowest_id)

        # Also limit by item count
        while len(self._items) > self.MAX_ITEMS:
            # Remove oldest item
            oldest_id = next(iter(self._items))
            removed = self._items.pop(oldest_id)

            # Clean up entity attention references
            for entity in removed.entities:
                if entity in self._entity_attention:
                    self._entity_attention[entity].context_items.discard(oldest_id)

    def _decay_expired(self):
        """Remove expired items based on TTL"""
        expired_ids = [
            item_id for item_id, item in self._items.items()
            if item.is_expired
        ]

        for item_id in expired_ids:
            removed = self._items.pop(item_id)

            # Clean up entity attention references
            for entity in removed.entities:
                if entity in self._entity_attention:
                    self._entity_attention[entity].context_items.discard(item_id)

    def get_context(self, max_tokens: int = None) -> str:
        """
        Get working memory context for generation

        Args:
            max_tokens: Maximum tokens to return (uses capacity if None)

        Returns:
            str: Formatted context string
        """
        # Decay expired items first
        self._decay_expired()

        # Update entity attention scores
        for attention in self._entity_attention.values():
            attention.update_attention()

        max_tokens = max_tokens or self.capacity

        # Sort by importance and recency
        sorted_items = sorted(
            self._items.values(),
            key=lambda x: (x.importance, x.timestamp),
            reverse=True
        )

        # Build context string
        parts = []
        current_tokens = 0

        for item in sorted_items:
            if current_tokens + item.token_estimate > max_tokens:
                break

            # Format based on type
            if item.item_type == "scene":
                parts.append(f"[当前场景]: {item.content}")
            elif item.item_type == "dialogue":
                parts.append(f"[当前对话]: {item.content}")
            elif item.item_type == "narrative":
                parts.append(f"[当前叙述]: {item.content}")
            else:
                parts.append(item.content)

            current_tokens += item.token_estimate

        # Add active entities
        active_entities = self.get_active_entities()
        if active_entities:
            parts.append(f"[活跃角色]: {', '.join(active_entities)}")

        return "\n".join(parts) if parts else ""

    def get_active_entities(self, min_attention: float = 0.3) -> List[str]:
        """
        Get entities with attention above threshold

        Args:
            min_attention: Minimum attention score

        Returns:
            List of active entity names, sorted by attention
        """
        # Decay and filter
        active = [
            (name, att.attention_score)
            for name, att in self._entity_attention.items()
            if att.attention_score >= min_attention
        ]

        # Sort by attention
        active.sort(key=lambda x: x[1], reverse=True)

        return [name for name, _ in active]

    def set_focus(self, focus: str, focus_type: str):
        """
        Set the current narrative focus

        Args:
            focus: What to focus on (e.g., character name)
            focus_type: Type of focus ("character", "location", "plot")
        """
        self._current_focus = focus
        self._focus_type = focus_type

        # Boost attention for focused entity
        if focus in self._entity_attention:
            self._entity_attention[focus].attention_score = 1.0

    def get_focus(self) -> Optional[tuple]:
        """Get current focus (focus, type)"""
        return (self._current_focus, self._focus_type) if self._current_focus else None

    def clear(self):
        """Clear working memory"""
        self._items.clear()
        self._entity_attention.clear()
        self._current_focus = None
        self._focus_type = None
        self._id_counter = 0
        self.save_to_disk()

    def save_to_disk(self):
        """Save working memory state to disk"""
        try:
            state = {
                "items": [item.to_dict() for item in self._items.values()],
                "entity_attention": {
                    name: {
                        "attention_score": att.attention_score,
                        "last_mention_time": att.last_mention_time,
                        "mention_count": att.mention_count,
                        "context_items": list(att.context_items)
                    }
                    for name, att in self._entity_attention.items()
                },
                "current_focus": self._current_focus,
                "focus_type": self._focus_type,
                "id_counter": self._id_counter,
                "last_saved": datetime.now().isoformat()
            }

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"保存工作记忆失败: {e}")

    def load_from_disk(self):
        """Load working memory state from disk"""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Restore items
            # 工作记忆的 TTL 表达的是"会话内活跃时长"，但 timestamp 以挂钟时间持久化。
            # 若按已流逝的真实时间判断过期，跨会话恢复（例如隔天续写）会把所有项
            # 立即判为过期而清空，等同于持久化失效。因此恢复时将 timestamp 重置为当前
            # 时间，让 TTL 从本次会话重新计时。
            now = time.time()
            for item_data in state.get("items", []):
                item = ContextItem(
                    id=item_data["id"],
                    content=item_data["content"],
                    item_type=item_data["item_type"],
                    timestamp=now,
                    ttl_seconds=item_data["ttl_seconds"],
                    importance=item_data.get("importance", 1.0),
                    entities=item_data.get("entities", []),
                    metadata=item_data.get("metadata", {})
                )
                self._items[item.id] = item

            # Restore entity attention（同理，last_mention_time 重置为当前时间，
            # 避免恢复后注意力分数因挂钟时间差被立即衰减为 0）
            for name, att_data in state.get("entity_attention", {}).items():
                attention = EntityAttention(
                    name=name,
                    attention_score=att_data.get("attention_score", 1.0),
                    last_mention_time=now,
                    mention_count=att_data.get("mention_count", 1),
                    context_items=set(att_data.get("context_items", []))
                )
                self._entity_attention[name] = attention

            # Restore focus
            self._current_focus = state.get("current_focus")
            self._focus_type = state.get("focus_type")

            # Restore counter
            self._id_counter = state.get("id_counter", 0)

        except Exception as e:
            print(f"加载工作记忆失败: {e}")
            self._items = OrderedDict()
            self._entity_attention = {}

    def to_text_description(self) -> str:
        """Convert working memory to text description for prompts"""
        self._decay_expired()

        parts = ["[工作记忆 - 当前活跃上下文]:"]

        # Current focus
        if self._current_focus:
            parts.append(f"当前焦点: {self._current_focus} ({self._focus_type})")

        # Active entities
        active_entities = self.get_active_entities()
        if active_entities:
            parts.append(f"活跃角色: {', '.join(active_entities[:5])}")

        # Recent context items
        context = self.get_context(max_tokens=500)
        if context:
            parts.append(f"\n{context}")

        return "\n".join(parts)

    def get_stats(self) -> Dict:
        """Get statistics about working memory"""
        return {
            "item_count": len(self._items),
            "entity_count": len(self._entity_attention),
            "total_tokens": sum(item.token_estimate for item in self._items.values()),
            "capacity": self.capacity,
            "utilization": (sum(item.token_estimate for item in self._items.values()) / self.capacity) if self.capacity else 0.0,
            "current_focus": self._current_focus,
            "active_entities": len(self.get_active_entities())
        }


# Backward compatibility: Adapter for sliding window
class WorkingMemoryAdapter:
    """
    Adapter to provide backward compatibility with sliding window interface
    while using working memory internally
    """

    def __init__(self, memory_dir: str = "memory_system"):
        self.working_memory = WorkingMemory(memory_dir=memory_dir)
        # Keep sliding window for persistence
        self._sliding_window_content: List[tuple] = []  # [(title, content), ...]

    def add_content(self, title: str, content: str):
        """Add content (compatible with sliding window)"""
        # Add to working memory
        self.working_memory.add_context(
            content=content,
            item_type="narrative",
            importance=0.8
        )

        # Also keep in sliding window for backward compatibility
        self._sliding_window_content.append((title, content))
        if len(self._sliding_window_content) > 10:
            self._sliding_window_content.pop(0)

    def get_context(self, max_chars: int = 3000) -> str:
        """Get context (compatible with sliding window)"""
        # Use working memory for rich context
        working_context = self.working_memory.get_context()

        # Fall back to sliding window if working memory is empty
        if not working_context and self._sliding_window_content:
            recent = self._sliding_window_content[-3:]
            return "\n".join(content for _, content in recent)[-max_chars:]

        return working_context

    def clear(self):
        """Clear memory"""
        self.working_memory.clear()
        self._sliding_window_content.clear()

    def load_from_disk(self):
        """Load from disk"""
        self.working_memory.load_from_disk()

    def save_to_disk(self):
        """Save to disk"""
        self.working_memory.save_to_disk()

    def to_text_description(self) -> str:
        """Convert to text description"""
        return self.working_memory.to_text_description()


# Test
if __name__ == "__main__":
    wm = WorkingMemory(capacity=500, default_ttl=60)

    # Add some context
    wm.add_context(
        content="李明走进房间，看到了王芳。",
        item_type="scene",
        entities=["李明", "王芳"],
        importance=1.0
    )

    wm.add_context(
        content='"你终于来了，"王芳说道，"我等了很久。"',
        item_type="dialogue",
        entities=["王芳"],
        importance=0.9
    )

    wm.set_focus("王芳", "character")

    print("Working Memory Context:")
    print(wm.get_context())
    print()

    print("Active Entities:")
    print(wm.get_active_entities())
    print()

    print("Stats:")
    print(wm.get_stats())
