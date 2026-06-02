#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Story Arc Controller
Multi-threaded narrative management with arc progression tracking

This module implements intelligent story arc management:
- Thread Management: Create, merge, suspend, and resolve story threads
- Arc Progression: Track setup → conflict → resolution progression
- Conflict Engine: Generate and manage narrative conflicts
- Interweaving: Coordinate multiple concurrent storylines

Key Features:
1. Multi-thread Support - Handle multiple concurrent plotlines
2. Arc Progression Tracking - Monitor story arc phases
3. Conflict Generation - Create meaningful conflicts
4. Thread Interweaving - Blend threads naturally
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Literal, Tuple
from datetime import datetime
from pathlib import Path
from enum import Enum
import math


class ThreadStatus(Enum):
    """Status of a story thread"""
    SETUP = "setup"           # Initial setup phase
    RISING = "rising"         # Tension building
    CLIMAX = "climax"         # Peak conflict
    FALLING = "falling"       # Resolution approaching
    RESOLVED = "resolved"     # Fully resolved
    SUSPENDED = "suspended"   # Temporarily paused


class ThreadPriority(Enum):
    """Priority level of a story thread"""
    MAIN = "main"             # Main plot thread
    MAJOR = "major"           # Major subplot
    MINOR = "minor"           # Minor subplot
    BACKGROUND = "background" # Background element


class ArcPhase(Enum):
    """Phases of a story arc"""
    EXPOSITION = "exposition"   # World/character introduction
    RISING_ACTION = "rising_action"  # Conflict development
    CLIMAX = "climax"           # Peak tension
    FALLING_ACTION = "falling_action"  # Consequences
    RESOLUTION = "resolution"   # Conclusion


@dataclass
class StoryThread:
    """
    A story thread (plotline/subplot)

    Attributes:
        id: Unique identifier
        title: Thread title
        description: What this thread is about
        priority: Main, major, minor, or background
        status: Current status
        phase: Current arc phase
        characters: Characters involved
        start_chapter: Chapter where thread started
        target_end_chapter: Planned end chapter
        current_chapter: Last updated chapter
        progress: 0-100 progress percentage
        conflicts: List of conflicts in this thread
        dependencies: Threads this depends on
        dependents: Threads that depend on this
        key_events: Important events in this thread
        metadata: Additional data
    """
    id: str
    title: str
    description: str = ""
    priority: ThreadPriority = ThreadPriority.MAJOR
    status: ThreadStatus = ThreadStatus.SETUP
    phase: ArcPhase = ArcPhase.EXPOSITION
    characters: List[str] = field(default_factory=list)
    start_chapter: int = 1
    target_end_chapter: Optional[int] = None
    current_chapter: int = 1
    progress: float = 0.0
    conflicts: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)
    key_events: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "phase": self.phase.value,
            "characters": self.characters,
            "start_chapter": self.start_chapter,
            "target_end_chapter": self.target_end_chapter,
            "current_chapter": self.current_chapter,
            "progress": self.progress,
            "conflicts": self.conflicts,
            "dependencies": self.dependencies,
            "dependents": self.dependents,
            "key_events": self.key_events,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'StoryThread':
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            priority=ThreadPriority(data.get("priority", "major")),
            status=ThreadStatus(data.get("status", "setup")),
            phase=ArcPhase(data.get("phase", "exposition")),
            characters=data.get("characters", []),
            start_chapter=data.get("start_chapter", 1),
            target_end_chapter=data.get("target_end_chapter"),
            current_chapter=data.get("current_chapter", 1),
            progress=data.get("progress", 0.0),
            conflicts=data.get("conflicts", []),
            dependencies=data.get("dependencies", []),
            dependents=data.get("dependents", []),
            key_events=data.get("key_events", []),
            metadata=data.get("metadata", {})
        )


@dataclass
class Conflict:
    """
    A narrative conflict

    Attributes:
        id: Conflict ID
        type: internal, interpersonal, societal, nature, supernatural
        parties: Characters/entities in conflict
        stakes: What's at stake
        intensity: 0-10 intensity level
        resolution_type: How it can be resolved
        status: active, escalating, resolved, stalemate
    """
    id: str
    type: str
    parties: List[str]
    stakes: str = ""
    intensity: float = 5.0
    resolution_type: str = "confrontation"
    status: str = "active"
    thread_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class StoryArcController:
    """
    Controller for managing story arcs and threads

    Features:
    - Multi-thread narrative management
    - Arc progression tracking
    - Conflict generation
    - Thread interweaving logic
    """

    def __init__(self, memory_dir: str = "memory_system"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # Threads storage
        self._threads: Dict[str, StoryThread] = {}
        self._conflicts: Dict[str, Conflict] = {}

        # ID counters
        self._thread_counter = 0
        self._conflict_counter = 0

        # Current chapter
        self._current_chapter = 1

        # Active thread (for focus)
        self._active_thread_id: Optional[str] = None

        # File
        self.data_file = self.memory_dir / "story_arcs.json"

        # Load
        self.load_from_disk()

        # LLM client for suggestions
        self._llm_client = None

    def _get_llm_client(self):
        """Get LLM client"""
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

    def _generate_thread_id(self) -> str:
        self._thread_counter += 1
        return f"thread_{self._thread_counter:03d}"

    def _generate_conflict_id(self) -> str:
        self._conflict_counter += 1
        return f"conflict_{self._conflict_counter:03d}"

    def create_thread(
        self,
        title: str,
        description: str = "",
        priority: str = "major",
        characters: List[str] = None,
        target_end: int = None,
        dependencies: List[str] = None
    ) -> StoryThread:
        """
        Create a new story thread

        Args:
            title: Thread title
            description: What this thread is about
            priority: main, major, minor, or background
            characters: Characters involved
            target_end: Planned end chapter
            dependencies: Thread IDs this depends on

        Returns:
            The created thread
        """
        thread = StoryThread(
            id=self._generate_thread_id(),
            title=title,
            description=description,
            priority=ThreadPriority(priority),
            characters=characters or [],
            start_chapter=self._current_chapter,
            target_end_chapter=target_end,
            dependencies=dependencies or [],
            current_chapter=self._current_chapter
        )

        # Update dependencies
        for dep_id in (dependencies or []):
            if dep_id in self._threads:
                self._threads[dep_id].dependents.append(thread.id)

        self._threads[thread.id] = thread
        self.save_to_disk()

        print(f"✓ 创建故事线 [{priority}]: {title}")

        return thread

    def advance_thread(
        self,
        thread_id: str,
        event: str = "",
        progress_delta: float = 10.0
    ) -> bool:
        """
        Advance a story thread

        Args:
            thread_id: Thread ID
            event: Event description
            progress_delta: Progress increment

        Returns:
            Success status
        """
        thread = self._threads.get(thread_id)
        if not thread:
            return False

        # Update progress
        thread.progress = min(100, thread.progress + progress_delta)
        thread.current_chapter = self._current_chapter

        # Record event
        if event:
            thread.key_events.append({
                "chapter": self._current_chapter,
                "event": event
            })

        # Update phase based on progress
        self._update_thread_phase(thread)

        self.save_to_disk()
        return True

    def _update_thread_phase(self, thread: StoryThread):
        """Update thread phase based on progress"""
        if thread.progress < 10:
            thread.phase = ArcPhase.EXPOSITION
            thread.status = ThreadStatus.SETUP
        elif thread.progress < 40:
            thread.phase = ArcPhase.RISING_ACTION
            thread.status = ThreadStatus.RISING
        elif thread.progress < 60:
            thread.phase = ArcPhase.CLIMAX
            thread.status = ThreadStatus.CLIMAX
        elif thread.progress < 90:
            thread.phase = ArcPhase.FALLING_ACTION
            thread.status = ThreadStatus.FALLING
        else:
            thread.phase = ArcPhase.RESOLUTION
            thread.status = ThreadStatus.RESOLVED

    def complete_thread(self, thread_id: str, resolution: str = "") -> bool:
        """Complete a story thread"""
        thread = self._threads.get(thread_id)
        if not thread:
            return False

        thread.status = ThreadStatus.RESOLVED
        thread.phase = ArcPhase.RESOLUTION
        thread.progress = 100.0

        if resolution:
            thread.metadata["resolution"] = resolution

        print(f"✓ 完成故事线: {thread.title}")

        self.save_to_disk()
        return True

    def suspend_thread(self, thread_id: str, reason: str = "") -> bool:
        """Suspend a story thread"""
        thread = self._threads.get(thread_id)
        if not thread:
            return False

        thread.status = ThreadStatus.SUSPENDED
        thread.metadata["suspend_reason"] = reason

        self.save_to_disk()
        return True

    def resume_thread(self, thread_id: str) -> bool:
        """Resume a suspended thread"""
        thread = self._threads.get(thread_id)
        if not thread or thread.status != ThreadStatus.SUSPENDED:
            return False

        # Restore to previous phase
        self._update_thread_phase(thread)

        self.save_to_disk()
        return True

    def merge_threads(self, thread_id1: str, thread_id2: str, new_title: str = None) -> Optional[StoryThread]:
        """
        Merge two threads into one

        Args:
            thread_id1: First thread
            thread_id2: Second thread
            new_title: Optional new title

        Returns:
            Merged thread or None
        """
        thread1 = self._threads.get(thread_id1)
        thread2 = self._threads.get(thread_id2)

        if not thread1 or not thread2:
            return None

        # Create merged thread
        merged = StoryThread(
            id=self._generate_thread_id(),
            title=new_title or f"{thread1.title} & {thread2.title}",
            description=f"合并自: {thread1.title}, {thread2.title}",
            priority=max(thread1.priority, thread2.priority, key=lambda p: p.value),
            characters=list(set(thread1.characters + thread2.characters)),
            start_chapter=min(thread1.start_chapter, thread2.start_chapter),
            progress=max(thread1.progress, thread2.progress),
            conflicts=thread1.conflicts + thread2.conflicts,
            current_chapter=self._current_chapter
        )

        # Mark originals as merged
        thread1.metadata["merged_into"] = merged.id
        thread2.metadata["merged_into"] = merged.id
        thread1.status = ThreadStatus.RESOLVED
        thread2.status = ThreadStatus.RESOLVED

        self._threads[merged.id] = merged
        self.save_to_disk()

        print(f"✓ 合并故事线: {thread1.title} + {thread2.title} → {merged.title}")

        return merged

    def create_conflict(
        self,
        type: str,
        parties: List[str],
        stakes: str = "",
        intensity: float = 5.0,
        thread_id: str = None
    ) -> Conflict:
        """
        Create a new conflict

        Args:
            type: internal, interpersonal, societal, nature, supernatural
            parties: Characters/entities in conflict
            stakes: What's at stake
            intensity: 0-10 intensity
            thread_id: Associated thread

        Returns:
            The created conflict
        """
        conflict = Conflict(
            id=self._generate_conflict_id(),
            type=type,
            parties=parties,
            stakes=stakes,
            intensity=intensity,
            thread_id=thread_id
        )

        self._conflicts[conflict.id] = conflict

        # Add to thread
        if thread_id and thread_id in self._threads:
            self._threads[thread_id].conflicts.append(conflict.id)

        self.save_to_disk()

        print(f"✓ 创建冲突 [{type}]: {' vs '.join(parties)}")

        return conflict

    def escalate_conflict(self, conflict_id: str, amount: float = 1.0) -> bool:
        """Escalate a conflict"""
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            return False

        conflict.intensity = min(10, conflict.intensity + amount)
        conflict.status = "escalating"

        self.save_to_disk()
        return True

    def resolve_conflict(self, conflict_id: str, resolution: str = "") -> bool:
        """Resolve a conflict"""
        conflict = self._conflicts.get(conflict_id)
        if not conflict:
            return False

        conflict.status = "resolved"
        conflict.metadata["resolution"] = resolution

        # Advance associated thread
        if conflict.thread_id and conflict.thread_id in self._threads:
            self.advance_thread(
                conflict.thread_id,
                event=f"解决冲突: {conflict.id}",
                progress_delta=15.0
            )

        self.save_to_disk()

        print(f"✓ 解决冲突: {conflict_id}")

        return True

    def get_active_threads(self) -> List[StoryThread]:
        """Get all active threads"""
        return [
            t for t in self._threads.values()
            if t.status not in [ThreadStatus.RESOLVED, ThreadStatus.SUSPENDED]
        ]

    def get_thread_by_priority(self, priority: str) -> List[StoryThread]:
        """Get threads by priority"""
        try:
            p = ThreadPriority(priority)
            return [t for t in self._threads.values() if t.priority == p]
        except ValueError:
            return []

    def get_threads_for_character(self, character: str) -> List[StoryThread]:
        """Get threads involving a character"""
        return [
            t for t in self._threads.values()
            if character in t.characters
        ]

    def set_active_thread(self, thread_id: str) -> bool:
        """Set the currently active thread"""
        if thread_id in self._threads:
            self._active_thread_id = thread_id
            return True
        return False

    def get_active_thread(self) -> Optional[StoryThread]:
        """Get the currently active thread"""
        if self._active_thread_id:
            return self._threads.get(self._active_thread_id)
        return None

    def get_thread_progression_summary(self) -> str:
        """Get summary of all thread progressions"""
        parts = ["[故事线进度概览]:"]

        for priority in [ThreadPriority.MAIN, ThreadPriority.MAJOR, ThreadPriority.MINOR]:
            threads = self.get_thread_by_priority(priority.value)
            if threads:
                parts.append(f"\n{priority.value.upper()}故事线:")
                for t in threads:
                    status_marker = "✓" if t.status == ThreadStatus.RESOLVED else "●"
                    parts.append(
                        f"  {status_marker} {t.title}: {t.progress:.0f}% "
                        f"[{t.phase.value}]"
                    )

        return "\n".join(parts)

    def get_generation_guidance(self) -> str:
        """
        Get guidance for current generation

        Returns:
            Formatted guidance for LLM prompt
        """
        parts = []

        # Active thread focus
        active = self.get_active_thread()
        if active:
            parts.append(f"[当前焦点故事线]: {active.title}")
            parts.append(f"  阶段: {active.phase.value}")
            parts.append(f"  进度: {active.progress:.0f}%")
            parts.append(f"  角色: {', '.join(active.characters)}")

        # Threads needing attention
        threads_needing_attention = [
            t for t in self.get_active_threads()
            if t.status == ThreadStatus.CLIMAX or t.progress > 80
        ]

        if threads_needing_attention:
            parts.append("\n[需要推进的故事线]:")
            for t in threads_needing_attention[:3]:
                parts.append(f"- {t.title} ({t.progress:.0f}%, {t.phase.value})")

        # Active conflicts
        active_conflicts = [
            c for c in self._conflicts.values()
            if c.status == "active"
        ]

        if active_conflicts:
            parts.append("\n[活跃冲突]:")
            for c in active_conflicts[:3]:
                parts.append(f"- {' vs '.join(c.parties)}: {c.stakes}")

        return "\n".join(parts) if parts else ""

    def suggest_next_event(self) -> Optional[str]:
        """Suggest what should happen next"""
        llm = self._get_llm_client()
        if not llm:
            return self._simple_suggestion()

        guidance = self.get_generation_guidance()
        prompt = f"""
        基于当前故事状态，建议下一个应该发生的关键事件：

        {guidance}

        请给出一个简短的事件建议（1-2句话）：
        """

        suggestion = llm.generate(prompt)
        return suggestion.strip() if suggestion else self._simple_suggestion()

    def _simple_suggestion(self) -> str:
        """Simple suggestion without LLM"""
        # Find thread needing progress
        for thread in self.get_active_threads():
            if thread.status == ThreadStatus.CLIMAX:
                return f"推进「{thread.title}」的高潮阶段"
            elif thread.progress > 70:
                return f"为「{thread.title}」准备结局"

        # Default
        return "发展当前的情节冲突"

    def update_chapter(self, chapter: int):
        """Update current chapter"""
        self._current_chapter = chapter
        for thread in self._threads.values():
            thread.current_chapter = chapter
        self.save_to_disk()

    def clear(self):
        """Clear all data"""
        self._threads.clear()
        self._conflicts.clear()
        self._thread_counter = 0
        self._conflict_counter = 0
        self._active_thread_id = None
        self.save_to_disk()

    def save_to_disk(self):
        """Save to disk"""
        try:
            data = {
                "threads": [t.to_dict() for t in self._threads.values()],
                "conflicts": [
                    {
                        "id": c.id,
                        "type": c.type,
                        "parties": c.parties,
                        "stakes": c.stakes,
                        "intensity": c.intensity,
                        "resolution_type": c.resolution_type,
                        "status": c.status,
                        "thread_id": c.thread_id,
                        "metadata": c.metadata
                    }
                    for c in self._conflicts.values()
                ],
                "thread_counter": self._thread_counter,
                "conflict_counter": self._conflict_counter,
                "current_chapter": self._current_chapter,
                "active_thread_id": self._active_thread_id,
                "last_saved": datetime.now().isoformat()
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存故事弧数据失败: {e}")

    def load_from_disk(self):
        """Load from disk"""
        if not self.data_file.exists():
            return

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for thread_data in data.get("threads", []):
                thread = StoryThread.from_dict(thread_data)
                self._threads[thread.id] = thread

            for conflict_data in data.get("conflicts", []):
                conflict = Conflict(
                    id=conflict_data["id"],
                    type=conflict_data["type"],
                    parties=conflict_data["parties"],
                    stakes=conflict_data.get("stakes", ""),
                    intensity=conflict_data.get("intensity", 5.0),
                    resolution_type=conflict_data.get("resolution_type", "confrontation"),
                    status=conflict_data.get("status", "active"),
                    thread_id=conflict_data.get("thread_id"),
                    metadata=conflict_data.get("metadata", {})
                )
                self._conflicts[conflict.id] = conflict

            self._thread_counter = data.get("thread_counter", 0)
            self._conflict_counter = data.get("conflict_counter", 0)
            self._current_chapter = data.get("current_chapter", 1)
            self._active_thread_id = data.get("active_thread_id")

        except Exception as e:
            print(f"加载故事弧数据失败: {e}")

    def get_stats(self) -> Dict:
        """Get statistics"""
        return {
            "thread_count": len(self._threads),
            "active_threads": len(self.get_active_threads()),
            "resolved_threads": len([t for t in self._threads.values() if t.status == ThreadStatus.RESOLVED]),
            "conflict_count": len(self._conflicts),
            "active_conflicts": len([c for c in self._conflicts.values() if c.status == "active"]),
            "current_chapter": self._current_chapter,
            "by_priority": {
                p.value: len([t for t in self._threads.values() if t.priority == p])
                for p in ThreadPriority
            }
        }


# Test
if __name__ == "__main__":
    controller = StoryArcController(memory_dir="test_memory")

    # Create threads
    main = controller.create_thread(
        title="寻找真相",
        description="主角调查父亲的失踪",
        priority="main",
        characters=["李明", "王芳"]
    )

    subplot = controller.create_thread(
        title="情感纠葛",
        description="李明和王芳的感情发展",
        priority="major",
        characters=["李明", "王芳"]
    )

    # Create conflict
    conflict = controller.create_conflict(
        type="interpersonal",
        parties=["李明", "神秘人"],
        stakes="真相的线索",
        intensity=7.0,
        thread_id=main.id
    )

    # Advance
    controller.advance_thread(main.id, "李明发现了新的线索", 20.0)
    controller.escalate_conflict(conflict.id, 2.0)

    # Print status
    print(controller.get_thread_progression_summary())
    print()
    print(controller.get_generation_guidance())
    print()
    print(f"Stats: {controller.get_stats()}")
