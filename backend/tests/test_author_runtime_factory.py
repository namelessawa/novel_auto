from __future__ import annotations

import os

import novel_manager
from story.models import GenerationModeConfig
from story.persistence import GenerationModeStore
from story.runtime import RuntimeFactory, clear_author_runtimes


def test_author_default_does_not_construct_simulation_agents(tmp_path, monkeypatch) -> None:
    root = str(tmp_path)
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", root)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", os.path.join(root, "users"))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", os.path.join(root, "novels")
    )
    clear_author_runtimes()
    novel = novel_manager.create_novel("alice", "默认作者")
    constructed = {"count": 0}

    def simulation_factory(**kwargs):
        constructed["count"] += 1
        return kwargs

    factory = RuntimeFactory(simulation_factory=simulation_factory)
    author = factory.create(user_id="alice", novel_id=novel["id"])

    assert author.mode == "author"
    assert author.simulation_agent_count == 0
    assert constructed["count"] == 0

    mode_store = GenerationModeStore(author.data_dir)
    mode_store.save(GenerationModeConfig(mode="simulation"))
    simulation = factory.create(user_id="alice", novel_id=novel["id"])
    assert simulation["novel_id"] == novel["id"]
    assert constructed["count"] == 1
