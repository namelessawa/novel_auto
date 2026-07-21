from __future__ import annotations

import json
from pathlib import Path

import pytest

from story.migrations import ensure_story_domain
from story.models import StoryBibleUpdate
from story.persistence import (
    CanonicalStateStore,
    DataCorruptionError,
    MemoryRepository,
    RevisionConflict,
    StoryBibleStore,
    StoryThreadStore,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_new_novel_gets_complete_author_domain(tmp_path: Path) -> None:
    report = ensure_story_domain(str(tmp_path), title="潮汐之城")

    assert report.status == "created"
    assert StoryBibleStore(str(tmp_path)).load().premise.startswith("围绕《潮汐之城》")
    assert CanonicalStateStore(str(tmp_path)).load().revision == 1
    assert StoryThreadStore(str(tmp_path)).load().threads == {}
    assert MemoryRepository(str(tmp_path)).load().records == {}
    assert (tmp_path / "generation_mode.json").is_file()


def test_legacy_migration_maps_authorities_and_excludes_legend_from_canon(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "tick_state.json",
        {
            "current_tick": 17,
            "world_state": {
                "world_time": 42,
                "era": "雾历",
                "locations": [{"id": "harbor", "name": "旧港"}],
                "world_rules": ["死亡不可逆"],
            },
            "character_profiles": {
                "a": {
                    "id": "a",
                    "name": "阿澜",
                    "importance_tier": "A",
                    "personality": "克制",
                }
            },
            "character_states": {
                "a": {
                    "character_id": "a",
                    "current_location": "harbor",
                    "inventory": ["铜钥匙"],
                    "known_facts": ["潮门将在午夜开启"],
                }
            },
            "open_loops": {
                "gate": {
                    "id": "gate",
                    "description": "谁会开启潮门",
                    "type": "mystery",
                    "promised_question": "潮门之后是什么？",
                    "urgency": 8,
                }
            },
            "reader_known_facts": [{"fact": "阿澜持有钥匙"}],
            "narrative_continuity_state": {"last_location": "harbor"},
            "story_arc": {
                "theme": "身份与牺牲",
                "central_question": "守住身份是否值得牺牲？",
                "current_act": 2,
            },
        },
    )
    _write_json(
        tmp_path / "fact_ledger.json",
        {
            "facts": [
                {
                    "id": "fact_key",
                    "kind": "possession",
                    "subject": "a",
                    "object": "铜钥匙",
                    "status": "active",
                }
            ]
        },
    )
    _write_json(
        tmp_path / "memory_store.json",
        {
            "records": [
                {
                    "entry": {
                        "id": "mem_first",
                        "summary": "阿澜在旧港拿到铜钥匙",
                        "importance": 9,
                        "involved": ["a"],
                    }
                }
            ]
        },
    )
    _write_json(
        tmp_path / "summary_tree.json",
        {
            "leaves": [{"node_id": "s1", "summary": "潮声吞没旧港"}],
            "legends": [
                {
                    "legend_id": "l1",
                    "legendary_form": "传说死者会从潮中归来",
                    "importance": 8,
                }
            ],
        },
    )

    report = ensure_story_domain(str(tmp_path), title="潮门")
    bible = StoryBibleStore(str(tmp_path)).load()
    state = CanonicalStateStore(str(tmp_path)).load()
    threads = StoryThreadStore(str(tmp_path)).load()
    memories = MemoryRepository(str(tmp_path)).load()

    assert report.status == "migrated"
    assert bible.theme == "身份与牺牲"
    assert bible.immutable_world_rules == ["死亡不可逆"]
    assert bible.migration.needs_confirmation is True
    assert state.world_time == 42
    assert state.characters["a"]["location"] == "harbor"
    assert state.character_knowledge["a"] == ["潮门将在午夜开启"]
    assert state.canonical_facts["fact_key"]["object"] == "铜钥匙"
    assert "l1" not in state.canonical_facts
    assert threads.threads["gate"].urgency == 8
    assert memories.records["legend_l1"].canon_status == "uncertain"
    assert memories.records["mem_first"].importance == 9


def test_migration_is_idempotent_and_does_not_replace_user_edit(tmp_path: Path) -> None:
    ensure_story_domain(str(tmp_path), title="初名")
    store = StoryBibleStore(str(tmp_path))
    first = store.load()
    edited = store.update(
        StoryBibleUpdate(
            expected_revision=first.revision,
            premise="一座城市每晚遗忘一个人。",
            theme="记忆与责任",
            setting_summary="潮汐城市",
        )
    )

    second_report = ensure_story_domain(str(tmp_path), title="改名不应覆盖")
    loaded = store.load()

    assert second_report.status == "created"
    assert loaded.revision == edited.revision == 2
    assert loaded.theme == "记忆与责任"
    assert loaded.migration.needs_confirmation is False


def test_story_bible_revision_conflict_is_explicit(tmp_path: Path) -> None:
    ensure_story_domain(str(tmp_path), title="冲突")
    store = StoryBibleStore(str(tmp_path))
    with pytest.raises(RevisionConflict) as error:
        store.update(
            StoryBibleUpdate(
                expected_revision=99,
                premise="前提",
                theme="主题",
                setting_summary="背景",
            )
        )
    assert error.value.actual == 1


def test_corrupt_legacy_source_is_preserved_and_migration_remains_usable(
    tmp_path: Path,
) -> None:
    original = "{broken"
    (tmp_path / "tick_state.json").write_text(original, encoding="utf-8")

    report = ensure_story_domain(str(tmp_path), title="损坏存档")

    assert report.status == "partial"
    assert (tmp_path / "tick_state.json").read_text(encoding="utf-8") == original
    assert list((tmp_path / "quarantine").glob("legacy_tick_state.json.*.corrupt"))
    assert StoryBibleStore(str(tmp_path)).load().theme


def test_atomic_store_recovers_last_good_backup_and_refuses_corrupt_overwrite(
    tmp_path: Path,
) -> None:
    ensure_story_domain(str(tmp_path), title="备份")
    store = StoryBibleStore(str(tmp_path))
    first = store.load()
    store.update(
        StoryBibleUpdate(
            expected_revision=1,
            premise="前提二",
            theme="主题二",
            setting_summary="背景二",
        )
    )
    Path(store.path).write_text("not-json", encoding="utf-8")

    recovered = store.load()
    assert recovered.revision == first.revision
    assert list((tmp_path / "quarantine").glob("story_bible.json.*.corrupt"))
    with pytest.raises(DataCorruptionError):
        store.save(recovered.model_copy(update={"revision": 2}))
