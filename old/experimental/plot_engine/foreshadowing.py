#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Foreshadowing Engine
Active management of foreshadowing hints with lifecycle tracking

This module implements an intelligent foreshadowing system:
- Planting: Automatically or manually plant hints
- Tracking: Monitor foreshadowing state and deadlines
- Resolution: Ensure proper payoff for planted hints

Key Features:
1. Lifecycle Management - Track hints from planting to resolution
2. Deadline Awareness - Alert when foreshadowing needs resolution
3. Validation - Check if resolution satisfies the hint
4. Suggestion - Generate resolution suggestions
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Literal, Tuple
from datetime import datetime
from pathlib import Path
from enum import Enum
import hashlib


class ForeshadowingType(Enum):
    """Types of foreshadowing"""
    MYSTERY = "mystery"        # Unresolved question
    CONFLICT = "conflict"      # Upcoming confrontation
    CHARACTER = "character"    # Character development hint
    THEME = "theme"           # Thematic resonance
    OBJECT = "object"         # Chekhov's gun type
    EVENT = "event"           # Future event hint
    RELATIONSHIP = "relationship"  # Relationship development


class ForeshadowingStatus(Enum):
    """Lifecycle states of foreshadowing"""
    PLANTED = "planted"       # Hint has been planted
    HINTED = "hinted"         # Hint has been reinforced
    DUE = "due"               # Due for resolution
    RESOLVED = "resolved"     # Successfully resolved
    ABANDONED = "abandoned"   # Abandoned without resolution


@dataclass
class Foreshadowing:
    """
    A foreshadowing hint with full lifecycle tracking

    Attributes:
        id: Unique identifier
        type: Type of foreshadowing
        hint_text: The actual hint text in the story
        planted_chapter: Chapter where hint was planted
        planted_context: Context around the hint
        target_range: (min_chapter, max_chapter) for resolution
        strength: How explicit the hint is
        status: Current lifecycle status
        resolution_criteria: What would constitute valid resolution
        resolution_text: Actual resolution text (when resolved)
        resolved_chapter: Chapter where resolved
        importance: How important this is to the story
        related_entities: Characters/locations involved
        metadata: Additional metadata
    """
    id: str
    type: ForeshadowingType
    hint_text: str
    planted_chapter: int
    planted_context: str = ""
    target_range: Tuple[int, int] = (1, 10)
    strength: Literal["subtle", "moderate", "explicit"] = "moderate"
    status: ForeshadowingStatus = ForeshadowingStatus.PLANTED
    resolution_criteria: str = ""
    resolution_text: Optional[str] = None
    resolved_chapter: Optional[int] = None
    importance: float = 0.5
    related_entities: List[str] = field(default_factory=list)
    reinforcement_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Check if foreshadowing is still active"""
        return self.status in [
            ForeshadowingStatus.PLANTED,
            ForeshadowingStatus.HINTED,
            ForeshadowingStatus.DUE
        ]

    @property
    def is_overdue(self) -> bool:
        """Check if foreshadowing is past its deadline"""
        # This would need current chapter context
        return self.status == ForeshadowingStatus.DUE

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "hint_text": self.hint_text,
            "planted_chapter": self.planted_chapter,
            "planted_context": self.planted_context,
            "target_range": list(self.target_range),
            "strength": self.strength,
            "status": self.status.value,
            "resolution_criteria": self.resolution_criteria,
            "resolution_text": self.resolution_text,
            "resolved_chapter": self.resolved_chapter,
            "importance": self.importance,
            "related_entities": self.related_entities,
            "reinforcement_count": self.reinforcement_count,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Foreshadowing':
        return cls(
            id=data["id"],
            type=ForeshadowingType(data["type"]),
            hint_text=data["hint_text"],
            planted_chapter=data["planted_chapter"],
            planted_context=data.get("planted_context", ""),
            target_range=tuple(data.get("target_range", [1, 10])),
            strength=data.get("strength", "moderate"),
            status=ForeshadowingStatus(data.get("status", "planted")),
            resolution_criteria=data.get("resolution_criteria", ""),
            resolution_text=data.get("resolution_text"),
            resolved_chapter=data.get("resolved_chapter"),
            importance=data.get("importance", 0.5),
            related_entities=data.get("related_entities", []),
            reinforcement_count=data.get("reinforcement_count", 0),
            metadata=data.get("metadata", {})
        )


class ForeshadowingEngine:
    """
    Engine for managing foreshadowing lifecycle

    Features:
    - Plant hints with target resolution window
    - Track hint status and deadlines
    - Alert when resolution is due
    - Validate and record resolutions
    - Suggest resolutions for pending hints
    """

    DEFAULT_RESOLUTION_WINDOW = 5  # Default chapters until resolution due

    def __init__(self, memory_dir: str = "memory_system"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Storage
        self._foreshadowings: Dict[str, Foreshadowing] = {}
        self._by_chapter: Dict[int, List[str]] = {}  # chapter -> foreshadowing IDs

        # ID counter
        self._id_counter = 0

        # Current chapter
        self._current_chapter = 1

        # File
        self.data_file = self.memory_dir / "foreshadowing.json"

        # LLM client for suggestions (lazy load)
        self._llm_client = None

        # Load
        self.load_from_disk()

    def _get_llm_client(self):
        """Get LLM client for suggestions"""
        if self._llm_client is None:
            try:
                from core.llm_client import LLMClient
                from core.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, MODEL_NAME
                self._llm_client = LLMClient(
                    api_key=DEEPSEEK_API_KEY,
                    base_url=DEEPSEEK_BASE_URL,
                    model_name=MODEL_NAME,
                    max_tokens=1024,
                    temperature=0.7
                )
            except ImportError:
                pass
        return self._llm_client

    def _generate_id(self) -> str:
        """Generate unique ID"""
        self._id_counter += 1
        return f"fore_{self._id_counter:04d}"

    def plant(
        self,
        hint_text: str,
        type: str,
        target_range: Tuple[int, int] = None,
        resolution_criteria: str = "",
        strength: str = "moderate",
        importance: float = 0.5,
        entities: List[str] = None,
        context: str = ""
    ) -> Foreshadowing:
        """
        Plant a foreshadowing hint

        Args:
            hint_text: The actual hint text
            type: Type of foreshadowing (mystery, conflict, character, theme, object, event)
            target_range: (min_chapter, max_chapter) for resolution
            resolution_criteria: What would constitute valid resolution
            strength: How explicit the hint is (subtle, moderate, explicit)
            importance: Story importance (0-1)
            entities: Related characters/locations
            context: Surrounding context

        Returns:
            The created Foreshadowing object
        """
        # Determine target range
        if target_range is None:
            min_ch = self._current_chapter + 2  # At least 2 chapters later
            max_ch = min_ch + self.DEFAULT_RESOLUTION_WINDOW
            target_range = (min_ch, max_ch)

        # Create foreshadowing
        fore = Foreshadowing(
            id=self._generate_id(),
            type=ForeshadowingType(type),
            hint_text=hint_text,
            planted_chapter=self._current_chapter,
            planted_context=context,
            target_range=target_range,
            strength=strength,
            resolution_criteria=resolution_criteria,
            importance=importance,
            related_entities=entities or []
        )

        # Store
        self._foreshadowings[fore.id] = fore

        if self._current_chapter not in self._by_chapter:
            self._by_chapter[self._current_chapter] = []
        self._by_chapter[self._current_chapter].append(fore.id)

        # Save
        self.save_to_disk()

        print(f"✓ 植入伏笔 [{fore.type.value}]: {hint_text[:50]}... (目标章节: {target_range[0]}-{target_range[1]})")

        return fore

    def reinforce(self, fore_id: str, additional_hint: str = "") -> bool:
        """
        Reinforce a foreshadowing hint

        Args:
            fore_id: Foreshadowing ID
            additional_hint: Additional hint text to add

        Returns:
            Success status
        """
        fore = self._foreshadowings.get(fore_id)
        if not fore or not fore.is_active:
            return False

        # Update status
        fore.status = ForeshadowingStatus.HINTED
        fore.reinforcement_count += 1

        if additional_hint:
            fore.metadata["additional_hints"] = fore.metadata.get("additional_hints", [])
            fore.metadata["additional_hints"].append(additional_hint)

        self.save_to_disk()
        return True

    def check_resolution_window(self) -> List[Foreshadowing]:
        """
        Check for foreshadowings due for resolution

        Returns:
            List of foreshadowings that need resolution
        """
        due = []

        for fore in self._foreshadowings.values():
            if not fore.is_active:
                continue

            min_ch, max_ch = fore.target_range

            # Mark as due if within window
            if self._current_chapter >= min_ch:
                if fore.status == ForeshadowingStatus.PLANTED:
                    fore.status = ForeshadowingStatus.DUE
                due.append(fore)

            # Alert if overdue
            if self._current_chapter > max_ch:
                print(f"⚠ 警告: 伏笔已超期 [{fore.id}]: {fore.hint_text[:50]}...")
                fore.metadata["overdue"] = True

        self.save_to_disk()
        return due

    def validate_resolution(self, fore: Foreshadowing, text: str) -> Tuple[bool, str]:
        """
        Validate if text properly resolves the foreshadowing

        Args:
            fore: Foreshadowing to resolve
            text: Proposed resolution text

        Returns:
            Tuple of (is_valid, reason)
        """
        # Basic validation
        if not fore.is_active:
            return (False, "Foreshadowing is not active")

        # Check if resolution criteria mentioned
        if fore.resolution_criteria:
            # Simple keyword check (could be enhanced with NLP)
            criteria_keywords = fore.resolution_criteria.lower().split()
            text_lower = text.lower()
            matches = sum(1 for kw in criteria_keywords if kw in text_lower)

            if matches < len(criteria_keywords) * 0.3:
                return (False, f"Resolution doesn't address criteria: {fore.resolution_criteria}")

        # Check related entities
        if fore.related_entities:
            entity_mentions = sum(1 for e in fore.related_entities if e in text)
            if entity_mentions == 0:
                return (False, "Resolution doesn't mention related entities")

        return (True, "Resolution validated")

    def resolve(
        self,
        fore_id: str,
        resolution_text: str,
        validate: bool = True
    ) -> Tuple[bool, str]:
        """
        Resolve a foreshadowing

        Args:
            fore_id: Foreshadowing ID
            resolution_text: The resolution text
            validate: Whether to validate the resolution

        Returns:
            Tuple of (success, message)
        """
        fore = self._foreshadowings.get(fore_id)
        if not fore:
            return (False, "Foreshadowing not found")

        if not fore.is_active:
            return (False, "Foreshadowing is not active")

        # Validate if requested
        if validate:
            is_valid, reason = self.validate_resolution(fore, resolution_text)
            if not is_valid:
                return (False, f"Validation failed: {reason}")

        # Record resolution
        fore.status = ForeshadowingStatus.RESOLVED
        fore.resolution_text = resolution_text
        fore.resolved_chapter = self._current_chapter

        # Calculate resolution quality
        planted = fore.planted_chapter
        target_min, target_max = fore.target_range
        resolved = self._current_chapter

        if target_min <= resolved <= target_max:
            fore.metadata["resolution_quality"] = "perfect"
        elif resolved < target_min:
            fore.metadata["resolution_quality"] = "early"
        else:
            fore.metadata["resolution_quality"] = "late"

        self.save_to_disk()

        print(f"✓ 伏笔已解决 [{fore.id}]: {fore.hint_text[:30]}... → {resolution_text[:30]}...")

        return (True, "Resolution recorded")

    def suggest_resolution(self, fore_id: str) -> Optional[str]:
        """
        Suggest a resolution for a foreshadowing

        Args:
            fore_id: Foreshadowing ID

        Returns:
            Suggested resolution text or None
        """
        fore = self._foreshadowings.get(fore_id)
        if not fore or not fore.is_active:
            return None

        llm = self._get_llm_client()
        if not llm:
            return self._generate_simple_suggestion(fore)

        # Generate suggestion using LLM
        prompt = f"""
        请为以下伏笔生成一个合适的解决方案建议：

        伏笔类型: {fore.type.value}
        伏笔内容: {fore.hint_text}
        植入章节: 第{fore.planted_chapter}章
        当前章节: 第{self._current_chapter}章
        解决标准: {fore.resolution_criteria}
        相关角色: {', '.join(fore.related_entities)}

        请生成一个简短的解决建议（1-2句话）：
        """

        suggestion = llm.generate(prompt)
        return suggestion.strip() if suggestion else self._generate_simple_suggestion(fore)

    def _generate_simple_suggestion(self, fore: Foreshadowing) -> str:
        """Generate simple suggestion without LLM"""
        templates = {
            ForeshadowingType.MYSTERY: f"揭示{fore.hint_text[:20]}背后的真相",
            ForeshadowingType.CONFLICT: f"让相关角色的冲突得到解决",
            ForeshadowingType.CHARACTER: f"展示角色关于'{fore.hint_text[:20]}'的变化",
            ForeshadowingType.THEME: f"在当前情境中呼应'{fore.hint_text[:20]}'的主题",
            ForeshadowingType.OBJECT: f"让'{fore.hint_text[:20]}'发挥关键作用",
            ForeshadowingType.EVENT: f"让预言的事件发生或产生转折",
            ForeshadowingType.RELATIONSHIP: f"让相关角色的关系得到发展"
        }
        return templates.get(fore.type, "解决这个伏笔")

    def get_active(self) -> List[Foreshadowing]:
        """Get all active foreshadowings"""
        return [f for f in self._foreshadowings.values() if f.is_active]

    def get_by_type(self, type: str) -> List[Foreshadowing]:
        """Get foreshadowings by type"""
        try:
            fore_type = ForeshadowingType(type)
            return [f for f in self._foreshadowings.values() if f.type == fore_type]
        except ValueError:
            return []

    def get_by_chapter(self, chapter: int) -> List[Foreshadowing]:
        """Get foreshadowings planted in a chapter"""
        ids = self._by_chapter.get(chapter, [])
        return [self._foreshadowings[i] for i in ids if i in self._foreshadowings]

    def abandon(self, fore_id: str, reason: str = "") -> bool:
        """Abandon a foreshadowing"""
        fore = self._foreshadowings.get(fore_id)
        if not fore:
            return False

        fore.status = ForeshadowingStatus.ABANDONED
        fore.metadata["abandon_reason"] = reason
        fore.metadata["abandoned_chapter"] = self._current_chapter

        self.save_to_disk()
        return True

    def update_chapter(self, chapter: int):
        """Update current chapter and check deadlines"""
        self._current_chapter = chapter
        self.check_resolution_window()

    def get_generation_hints(self) -> str:
        """
        Get hints for the current generation

        Returns:
            Formatted hints for LLM prompt
        """
        parts = []

        # Active foreshadowings that could be addressed
        active = self.get_active()

        # Due foreshadowings (high priority)
        due = [f for f in active if f.status == ForeshadowingStatus.DUE]
        if due:
            parts.append("[待解决伏笔]:")
            for f in due[:3]:
                parts.append(f"- {f.type.value}: {f.hint_text}")
                if f.resolution_criteria:
                    parts.append(f"  解决标准: {f.resolution_criteria}")

        # Recently planted (could be reinforced)
        recent = [f for f in active if f.planted_chapter >= self._current_chapter - 2]
        if recent:
            parts.append("\n[近期伏笔]:")
            for f in recent[:3]:
                parts.append(f"- {f.type.value}: {f.hint_text}")

        return "\n".join(parts) if parts else ""

    def clear(self):
        """Clear all foreshadowings"""
        self._foreshadowings.clear()
        self._by_chapter.clear()
        self._id_counter = 0
        self.save_to_disk()

    def save_to_disk(self):
        """Save to disk"""
        try:
            data = {
                "foreshadowings": [f.to_dict() for f in self._foreshadowings.values()],
                "id_counter": self._id_counter,
                "current_chapter": self._current_chapter,
                "last_saved": datetime.now().isoformat()
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存伏笔数据失败: {e}")

    def load_from_disk(self):
        """Load from disk"""
        if not self.data_file.exists():
            return

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for fore_data in data.get("foreshadowings", []):
                fore = Foreshadowing.from_dict(fore_data)
                self._foreshadowings[fore.id] = fore

                if fore.planted_chapter not in self._by_chapter:
                    self._by_chapter[fore.planted_chapter] = []
                self._by_chapter[fore.planted_chapter].append(fore.id)

            self._id_counter = data.get("id_counter", 0)
            self._current_chapter = data.get("current_chapter", 1)

        except Exception as e:
            print(f"加载伏笔数据失败: {e}")

    def get_stats(self) -> Dict:
        """Get statistics"""
        active = self.get_active()
        resolved = [f for f in self._foreshadowings.values() if f.status == ForeshadowingStatus.RESOLVED]
        abandoned = [f for f in self._foreshadowings.values() if f.status == ForeshadowingStatus.ABANDONED]

        return {
            "total": len(self._foreshadowings),
            "active": len(active),
            "resolved": len(resolved),
            "abandoned": len(abandoned),
            "due": len([f for f in active if f.status == ForeshadowingStatus.DUE]),
            "by_type": {
                t.value: len([f for f in self._foreshadowings.values() if f.type == t])
                for t in ForeshadowingType
            }
        }


# Test
if __name__ == "__main__":
    engine = ForeshadowingEngine(memory_dir="test_memory")

    # Plant some foreshadowings
    f1 = engine.plant(
        hint_text="李明在抽屉里发现了一把旧钥匙",
        type="object",
        resolution_criteria="钥匙打开重要的门或盒子",
        entities=["李明"],
        strength="subtle"
    )

    f2 = engine.plant(
        hint_text="王芳提到她有一个失散多年的妹妹",
        type="mystery",
        resolution_criteria="妹妹的身份被揭示",
        entities=["王芳"],
        strength="moderate"
    )

    # Update chapter and check
    engine.update_chapter(5)
    due = engine.check_resolution_window()
    print(f"\nDue for resolution: {len(due)}")

    # Suggest resolution
    print(f"\nSuggestion for f1: {engine.suggest_resolution(f1.id)}")

    # Resolve
    success, msg = engine.resolve(f1.id, "李明用钥匙打开了尘封已久的书房，发现了父亲的日记。")
    print(f"\nResolution: {success} - {msg}")

    # Stats
    print(f"\nStats: {engine.get_stats()}")
