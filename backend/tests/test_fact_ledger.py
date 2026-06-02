"""Tests for FactLedger — 持久化 + 矛盾检测 + 时间线索引。"""

from __future__ import annotations

import pytest

from narrative.fact_ledger import Fact, FactConflict, FactLedger, TimelineEntry


def _f(
    fid: str,
    *,
    kind: str = "location",
    subject: str = "alice",
    predicate: str = "loc_castle",
    obj: str = "",
    tick: int = 0,
    src: str = "",
    status: str = "active",
) -> Fact:
    return Fact(
        id=fid,
        kind=kind,  # type: ignore[arg-type]
        subject=subject,
        predicate=predicate,
        object=obj,
        established_tick=tick,
        source_event_id=src,
        status=status,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 基础 CRUD
# ---------------------------------------------------------------------------


def test_assert_and_get(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1"))
    assert led.size == 1
    assert led.get("f1") is not None


def test_facts_about_filter_by_kind(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", kind="location"))
    led.assert_fact(_f("f2", kind="skill", predicate="剑术"))
    led.assert_fact(_f("f3", subject="bob"))
    assert len(led.facts_about("alice")) == 2
    assert len(led.facts_about("alice", kind="skill")) == 1
    assert len(led.facts_about("bob")) == 1


def test_current_location_of(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", predicate="loc_a", tick=10))
    assert led.current_location_of("alice") == "loc_a"
    led.assert_fact(_f("f2", predicate="loc_b", tick=20))
    assert led.current_location_of("alice") == "loc_b"


def test_is_dead(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    assert led.is_dead("alice") is False
    led.assert_fact(_f("d1", kind="death", predicate="心脏衰竭", tick=50))
    assert led.is_dead("alice") is True


# ---------------------------------------------------------------------------
# 时间线索引
# ---------------------------------------------------------------------------


def test_location_at_tick_returns_latest_before_tick(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", predicate="loc_a", tick=10))
    led.assert_fact(_f("f2", predicate="loc_b", tick=20))
    led.assert_fact(_f("f3", predicate="loc_c", tick=40))
    assert led.location_at_tick("alice", 5) is None
    assert led.location_at_tick("alice", 15) == "loc_a"
    assert led.location_at_tick("alice", 30) == "loc_b"
    assert led.location_at_tick("alice", 100) == "loc_c"


def test_location_timeline_preserves_tick_order(tmp_path) -> None:
    """乱序 assert 也要按 tick 升序维护 timeline。"""
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", predicate="loc_b", tick=20))
    led.assert_fact(_f("f2", predicate="loc_a", tick=10))
    led.assert_fact(_f("f3", predicate="loc_c", tick=30))
    assert led.location_at_tick("alice", 15) == "loc_a"
    assert led.location_at_tick("alice", 25) == "loc_b"


# ---------------------------------------------------------------------------
# 矛盾检测 — 不修改账本
# ---------------------------------------------------------------------------


def test_contradict_check_detects_two_locations_same_subject(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", predicate="loc_a", tick=10))
    new = _f("f2", predicate="loc_b", tick=10)
    conflicts = led.contradict_check(new)
    assert len(conflicts) == 1
    assert conflicts[0].severity == "high"
    # 检测不写入 — 旧 fact 仍 active
    assert led.get("f1").status == "active"


def test_contradict_check_dead_subject_action(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("d1", kind="death", predicate="疫病", tick=50))
    new_skill = _f("s1", kind="skill", predicate="剑术", tick=60)
    conflicts = led.contradict_check(new_skill)
    assert any(c.reason.startswith("已死亡") for c in conflicts)


def test_contradict_check_possession_two_owners(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(
        _f("p1", kind="possession", subject="alice", obj="石头剑", tick=10)
    )
    new = _f(
        "p2", kind="possession", subject="bob", obj="石头剑", tick=15
    )
    conflicts = led.contradict_check(new)
    assert any("同时被" in c.reason for c in conflicts)


def test_contradict_check_clean_returns_empty(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", predicate="loc_a", tick=10))
    new = _f("f2", subject="bob", predicate="loc_b", tick=10)
    assert led.contradict_check(new) == []


# ---------------------------------------------------------------------------
# 冲突动作: dispute / supersede / keep_old
# ---------------------------------------------------------------------------


def test_assert_dispute_default_marks_old_disputed(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", predicate="loc_a", tick=10))
    led.assert_fact(_f("f2", predicate="loc_b", tick=10))
    assert led.get("f1").status == "disputed"
    assert led.get("f2").status == "active"
    assert led.current_location_of("alice") == "loc_b"


def test_assert_supersede_marks_old_superseded(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", predicate="loc_a", tick=10))
    led.assert_fact(_f("f2", predicate="loc_b", tick=20), contradict_action="supersede")
    assert led.get("f1").status == "superseded"
    assert led.get("f1").superseded_by == "f2"


def test_assert_keep_old_marks_new_disputed(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", predicate="loc_a", tick=10))
    led.assert_fact(_f("f2", predicate="loc_b", tick=10), contradict_action="keep_old")
    assert led.get("f1").status == "active"
    assert led.get("f2").status == "disputed"
    assert led.current_location_of("alice") == "loc_a"


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def test_save_load_roundtrip(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    led.assert_fact(_f("f1", predicate="loc_a", tick=10))
    led.assert_fact(_f("d1", kind="death", predicate="伤病", tick=20))
    led.save()

    fresh = FactLedger(str(tmp_path))
    assert fresh.load() is True
    assert fresh.size == 2
    assert fresh.current_location_of("alice") == "loc_a"
    assert fresh.is_dead("alice") is True
    assert fresh.location_at_tick("alice", 15) == "loc_a"


def test_load_missing_returns_false(tmp_path) -> None:
    led = FactLedger(str(tmp_path))
    assert led.load() is False


# ---------------------------------------------------------------------------
# 综合 — 模拟"滚雪球矛盾"场景
# ---------------------------------------------------------------------------


def test_snowball_contradiction_chain_does_not_silently_overwrite(tmp_path) -> None:
    """五次相互矛盾的位置 assert, 应留下 disputed 痕迹 — 不能悄悄演化为另一条线。"""
    led = FactLedger(str(tmp_path))
    for i, loc in enumerate(["loc_a", "loc_b", "loc_a", "loc_c", "loc_a"]):
        led.assert_fact(_f(f"f{i}", predicate=loc, tick=10 + i))
    # 最新 (f4: loc_a) 为 active, 前 4 条均 disputed
    assert led.get("f4").status == "active"
    assert all(led.get(f"f{i}").status == "disputed" for i in range(4))
    # 账本可被审计 — 留下矛盾历史而不是吞掉
    statuses = [led.get(f"f{i}").status for i in range(5)]
    assert statuses.count("active") == 1
    assert statuses.count("disputed") == 4
