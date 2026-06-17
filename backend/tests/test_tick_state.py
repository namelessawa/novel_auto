"""TickState 持久化与 OpenLoop 自动过期的单元测试。"""

from __future__ import annotations

import os

from memory.tick_state import TickState
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    OpenLoop,
    StyleAnchor,
    WorldState,
)


def _make_state(tmp_dir: str) -> TickState:
    return TickState(data_dir=tmp_dir)


def test_advance_tick_increments(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    assert ts.current_tick == 0
    assert ts.advance_tick() == 1
    assert ts.advance_tick() == 2
    assert ts.current_tick == 2


def test_open_loop_sort_by_urgency(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    ts.add_open_loop(OpenLoop(id="l1", opened_tick=1, description="low", urgency=2))
    ts.add_open_loop(OpenLoop(id="l2", opened_tick=2, description="high", urgency=9))
    ts.add_open_loop(OpenLoop(id="l3", opened_tick=3, description="mid", urgency=5))

    loops = ts.get_open_loops()
    assert [l.id for l in loops] == ["l2", "l3", "l1"]

    high_only = ts.get_open_loops(min_urgency=6)
    assert [l.id for l in high_only] == ["l2"]


def test_reap_stale_open_loops(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    ts.add_open_loop(
        OpenLoop(
            id="old",
            opened_tick=10,
            description="stale",
            urgency=3,
            max_age_ticks=50,
        )
    )
    ts.add_open_loop(
        OpenLoop(
            id="fresh",
            opened_tick=80,
            description="recent",
            urgency=3,
            max_age_ticks=50,
        )
    )
    reaped = ts.reap_stale_open_loops(current_tick=100)
    assert reaped == ["old"]
    assert ts.get_open_loop_count() == 1


def test_style_anchor_top_k_sorted_by_weight(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    ts.add_style_anchor(StyleAnchor(excerpt="low", weight=0.3))
    ts.add_style_anchor(StyleAnchor(excerpt="high", weight=2.0))
    ts.add_style_anchor(StyleAnchor(excerpt="mid", weight=1.0))

    top = ts.get_style_anchors(top_k=2)
    assert [a.excerpt for a in top] == ["high", "mid"]


def test_persist_round_trip(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    ts.advance_tick()
    ts.advance_tick()
    ts.set_world_state(WorldState(world_time=42, era="冰封纪", weather="雪"))
    ts.upsert_character_profile(
        CharacterProfile(id="alice", name="Alice", importance_tier="A")
    )
    ts.upsert_character_state(
        CharacterState(
            character_id="alice",
            current_location="北境",
            known_facts=["父亲是骑士"],
            arc_progress=0.4,
            arc_goal="复仇",
        )
    )
    ts.add_open_loop(
        OpenLoop(id="murder", opened_tick=1, description="谁杀的父亲", urgency=8)
    )
    ts.add_style_anchor(StyleAnchor(excerpt="风停在城墙之外", weight=1.5))
    ts.record_last_event_tick("exogenous", 2)
    ts.save()

    # 重新构造同 data_dir 实例,验证 load 完整恢复
    ts2 = _make_state(str(tmp_path))
    assert ts2.load() is True
    assert ts2.current_tick == 2
    assert ts2.world_time == 42
    assert ts2.world_state.era == "冰封纪"
    assert ts2.get_character_profile("alice").importance_tier == "A"
    state = ts2.get_character_state("alice")
    assert state is not None and state.arc_progress == 0.4
    assert ts2.get_open_loop_count() == 1
    assert ts2.get_open_loops()[0].id == "murder"
    assert ts2.get_style_anchors()[0].excerpt == "风停在城墙之外"
    assert ts2.ticks_since_last_event("exogenous", current_tick=5) == 3


def test_load_missing_file_starts_fresh(tmp_path) -> None:
    ts = _make_state(str(tmp_path / "nonexistent"))
    assert ts.load() is False


def test_style_preset_key_default_empty(tmp_path) -> None:
    """Phase 5+: fresh TickState 的 style_preset_key = "" — narrator 默认行为."""
    ts = _make_state(str(tmp_path))
    assert ts.style_preset_key == ""


def test_style_preset_key_setter_strips(tmp_path) -> None:
    """Phase 5+: setter 去前后空白, 空字符串视作 '清空'."""
    ts = _make_state(str(tmp_path))
    ts.set_style_preset_key("  hot_blooded  ")
    assert ts.style_preset_key == "hot_blooded"
    ts.set_style_preset_key("")
    assert ts.style_preset_key == ""


def test_style_preset_key_persist_roundtrip(tmp_path) -> None:
    """Phase 5+: save → load 后 style_preset_key 恢复 — bootstrap CLI 写入,
    server 重启后 narrator 应当读到原值."""
    ts = _make_state(str(tmp_path))
    ts.set_style_preset_key("xianxia_fast")
    ts.save()

    ts2 = _make_state(str(tmp_path))
    assert ts2.load() is True
    assert ts2.style_preset_key == "xianxia_fast"


def test_style_preset_key_load_missing_field_defaults_empty(tmp_path) -> None:
    """Phase 5+ 向后兼容: 老 tick_state.json 没 style_preset_key 字段时 load
    成 "", narrator 走默认行为. 防 Phase 5 之前的小说升级时炸."""
    import json
    import os

    # 模拟一个老 payload (无 style_preset_key 字段)
    legacy = {
        "version": 1,
        "current_tick": 5,
        "last_narration_tick": 4,
        "novel_title": "老小说",
        "world_state": {},
        "character_profiles": {},
        "character_states": {},
        "open_loops": {},
        "style_anchors": [],
        "last_event_tick_by_type": {},
        "novelty_warnings": [],
        "story_arc": None,
        "agent_runtime_states": {},
    }
    legacy_path = os.path.join(str(tmp_path), "tick_state.json")
    with open(legacy_path, "w", encoding="utf-8") as f:
        json.dump(legacy, f, ensure_ascii=False)

    ts = _make_state(str(tmp_path))
    assert ts.load() is True
    assert ts.style_preset_key == ""
    assert ts.current_tick == 5
    assert ts.novel_title == "老小说"


def test_arc_status_excludes_c_tier(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    ts.upsert_character_profile(
        CharacterProfile(id="alice", name="Alice", importance_tier="A")
    )
    ts.upsert_character_profile(
        CharacterProfile(id="npc", name="NPC", importance_tier="C")
    )
    ts.upsert_character_state(CharacterState(character_id="alice", arc_progress=0.6))
    ts.upsert_character_state(CharacterState(character_id="npc", arc_progress=0.5))
    arcs = ts.get_arc_status()
    assert arcs == {"alice": 0.6}


def test_touch_open_loop_updates_reference_tick(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    ts.add_open_loop(
        OpenLoop(id="l1", opened_tick=1, description="x", urgency=5, last_referenced_tick=0)
    )
    ts.touch_open_loop("l1", tick=42)
    assert ts.get_open_loops()[0].last_referenced_tick == 42


# v2.38 Phase 2 Stage 3 (iter#91) — _loops_closed_total accounting
# ---------------------------------------------------------------------------


def test_loops_closed_total_starts_zero(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    assert ts.loops_closed_total == 0


def test_loops_closed_total_increments_on_close(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    ts.add_open_loop(OpenLoop(id="l1", opened_tick=0, description="x", urgency=5))
    ts.add_open_loop(OpenLoop(id="l2", opened_tick=0, description="y", urgency=5))
    ts.close_open_loop("l1")
    assert ts.loops_closed_total == 1
    ts.close_open_loop("l2")
    assert ts.loops_closed_total == 2
    # close 不存在的 id 不增加
    ts.close_open_loop("does_not_exist")
    assert ts.loops_closed_total == 2


def test_loops_closed_total_increments_on_reap(tmp_path) -> None:
    ts = _make_state(str(tmp_path))
    ts.add_open_loop(
        OpenLoop(id="l1", opened_tick=0, description="x", urgency=5, max_age_ticks=10)
    )
    ts.add_open_loop(
        OpenLoop(id="l2", opened_tick=0, description="y", urgency=5, max_age_ticks=100)
    )
    # tick 50 → l1 stale, l2 仍活
    reaped = ts.reap_stale_open_loops(current_tick=50)
    assert reaped == ["l1"]
    assert ts.loops_closed_total == 1
    assert ts.get_open_loop_count() == 1


def test_loops_closed_total_persists_roundtrip(tmp_path) -> None:
    """save → load 后累计数恢复."""
    ts = _make_state(str(tmp_path))
    ts.add_open_loop(OpenLoop(id="l1", opened_tick=0, description="x", urgency=5))
    ts.close_open_loop("l1")
    ts.add_open_loop(OpenLoop(id="l2", opened_tick=0, description="y", urgency=5))
    ts.close_open_loop("l2")
    assert ts.loops_closed_total == 2
    ts.save()
    ts2 = _make_state(str(tmp_path))
    assert ts2.load() is True
    assert ts2.loops_closed_total == 2
