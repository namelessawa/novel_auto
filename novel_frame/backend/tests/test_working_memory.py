"""Tests for the Working Memory module."""

import asyncio
import pytest

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from memory.working_memory import WorkingMemory, SceneContext, ActiveCharacter
from core.models import Section


def make_section(ch: int, sec: int, content: str = "test") -> Section:
    return Section(
        chapter=ch, section=sec, title=f"s{sec}", content=content, word_count=len(content)
    )


def test_push_and_retrieve():
    wm = WorkingMemory(capacity=3)
    loop = asyncio.new_event_loop()

    loop.run_until_complete(wm.push(make_section(1, 1, "aaa")))
    loop.run_until_complete(wm.push(make_section(1, 2, "bbb")))

    assert len(wm.sections) == 2
    assert wm.recent_text == "aaa\n\nbbb"
    loop.close()


def test_eviction():
    wm = WorkingMemory(capacity=2)
    evicted = []

    async def on_evict(section):
        evicted.append(section)

    wm.register_evict_callback(on_evict)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(wm.push(make_section(1, 1, "a")))
    loop.run_until_complete(wm.push(make_section(1, 2, "b")))
    loop.run_until_complete(wm.push(make_section(1, 3, "c")))

    assert len(wm.sections) == 2
    assert len(evicted) == 1
    assert evicted[0].section == 1
    loop.close()


def test_scene_context():
    wm = WorkingMemory(capacity=3)
    wm.update_scene(SceneContext(
        environment_description="dark forest",
        active_characters=[
            ActiveCharacter(entity_id="hero", name="Hero", emotion="angry")
        ],
    ))

    block = wm.to_prompt_block()
    assert "dark forest" in block
    assert "Hero(angry)" in block


def test_clear():
    wm = WorkingMemory(capacity=3)
    loop = asyncio.new_event_loop()
    loop.run_until_complete(wm.push(make_section(1, 1)))
    wm.clear()
    assert len(wm.sections) == 0
    assert wm.scene.environment_description == ""
    loop.close()
