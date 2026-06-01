"""Working Memory — ring-buffer / sliding window over recent sections."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Coroutine

from core.models import Section


@dataclass
class ActiveCharacter:
    entity_id: str
    name: str
    emotion: str = "neutral"


@dataclass
class SceneContext:
    environment_description: str = ""
    active_characters: list[ActiveCharacter] = field(default_factory=list)


class WorkingMemory:
    """Ring buffer that holds the most recent N sections plus scene context."""

    def __init__(self, capacity: int = 3) -> None:
        self._buffer: deque[Section] = deque(maxlen=capacity)
        self._scene = SceneContext()
        self._on_evict_callbacks: list[
            Callable[[Section], Coroutine]
        ] = []

    # -- public api -----------------------------------------------------------

    @property
    def scene(self) -> SceneContext:
        return self._scene

    @property
    def sections(self) -> list[Section]:
        return list(self._buffer)

    @property
    def recent_text(self) -> str:
        return "\n\n".join(s.content for s in self._buffer)

    def register_evict_callback(
        self, callback: Callable[[Section], Coroutine]
    ) -> None:
        self._on_evict_callbacks.append(callback)

    async def push(self, section: Section) -> None:
        evicted: Section | None = None
        if len(self._buffer) == self._buffer.maxlen:
            evicted = self._buffer[0]
        self._buffer.append(section)
        if evicted is not None:
            for cb in self._on_evict_callbacks:
                await cb(evicted)

    def update_scene(self, scene: SceneContext) -> None:
        self._scene = scene

    def clear(self) -> None:
        self._buffer.clear()
        self._scene = SceneContext()

    def to_prompt_block(self) -> str:
        parts: list[str] = []
        if self._scene.environment_description:
            parts.append(f"【当前场景】\n{self._scene.environment_description}")
        if self._scene.active_characters:
            chars = ", ".join(
                f"{c.name}({c.emotion})" for c in self._scene.active_characters
            )
            parts.append(f"【在场角色】{chars}")
        if self._buffer:
            parts.append("【前文内容】")
            for s in self._buffer:
                parts.append(
                    f"--- 第{s.chapter}章 第{s.section}节 {s.title} ---\n{s.content}"
                )
        return "\n\n".join(parts)
