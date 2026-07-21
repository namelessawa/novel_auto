"""Lazy runtime factory: author is default; simulation is explicit."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import novel_manager
from story.migrations import ensure_story_domain
from story.persistence import GenerationModeStore
from story.service import AuthorGenerationService


class AuthorRuntime:
    mode = "author"
    simulation_agent_count = 0

    def __init__(self, *, user_id: str, novel_id: str, writer=None) -> None:
        novel = novel_manager.get_novel(user_id, novel_id)
        if novel is None:
            raise KeyError(novel_id)
        self.user_id = user_id
        self.novel_id = novel_id
        self.data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
        self.migration = ensure_story_domain(
            self.data_dir, title=str(novel.get("title") or "")
        )
        self.service = AuthorGenerationService(
            user_id=user_id,
            novel_id=novel_id,
            data_dir=self.data_dir,
            title=str(novel.get("title") or ""),
            writer=writer,
        )


class RuntimeFactory:
    def __init__(
        self,
        simulation_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._simulation_factory = simulation_factory

    def create(self, *, user_id: str, novel_id: str, mode: str | None = None):
        data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)
        ensure_story_domain(
            data_dir,
            title=str((novel_manager.get_novel(user_id, novel_id) or {}).get("title") or ""),
        )
        selected = mode or GenerationModeStore(data_dir).load().mode
        if selected == "author":
            return AuthorRuntime(user_id=user_id, novel_id=novel_id)
        if selected != "simulation":
            raise ValueError(f"unsupported generation mode: {selected}")
        factory = self._simulation_factory
        if factory is None:
            # Lazy import is the important boundary: author mode does not even
            # import, let alone instantiate, the nine-agent Tick runtime.
            from tick_runtime import TickRuntime

            factory = TickRuntime
        return factory(user_id=user_id, novel_id=novel_id)


_author_runtimes: dict[tuple[str, str], AuthorRuntime] = {}
_lock = threading.RLock()


def get_author_runtime(user_id: str, novel_id: str) -> AuthorRuntime:
    key = (user_id, novel_id)
    with _lock:
        runtime = _author_runtimes.get(key)
        if runtime is None:
            runtime = AuthorRuntime(user_id=user_id, novel_id=novel_id)
            _author_runtimes[key] = runtime
        return runtime


def drop_author_runtime(user_id: str, novel_id: str) -> None:
    with _lock:
        _author_runtimes.pop((user_id, novel_id), None)


def clear_author_runtimes() -> None:
    with _lock:
        _author_runtimes.clear()


__all__ = [
    "AuthorRuntime",
    "RuntimeFactory",
    "clear_author_runtimes",
    "drop_author_runtime",
    "get_author_runtime",
]
