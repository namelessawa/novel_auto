"""TickDB.get_world_time_map — Phase 6-B reader API support.

Phase 6-B reader endpoint `/api/tick/narratives` 承诺返回 ``world_time`` 但 v2.48
ship 时漏填. 本 test 锁住 batch tick_id→world_time 映射的行为契约:

* empty input → empty dict
* 单 tick / 多 tick / 重复 tick / 缺失 tick 都有正确处理
* row_factory 配置正确 (sqlite3.Row 字段访问)
"""

from __future__ import annotations

from memory_system.models import TickSummary
from persistence.tick_db import TickDB


def _summary(tick: int, world_time: int = 0) -> TickSummary:
    return TickSummary(
        tick=tick,
        world_time=world_time,
        agents_called=["orch"],
        events_generated=[],
        narrator_produced_text=False,
        narrator_output_chars=0,
    )


def test_world_time_map_empty_input(tmp_path) -> None:
    db = TickDB(str(tmp_path / "ticks.db"))
    try:
        assert db.get_world_time_map([]) == {}
    finally:
        db.close()


def test_world_time_map_returns_tick_to_world_time(tmp_path) -> None:
    db = TickDB(str(tmp_path / "ticks.db"))
    try:
        db.insert_tick(_summary(tick=1, world_time=100))
        db.insert_tick(_summary(tick=2, world_time=200))
        db.insert_tick(_summary(tick=5, world_time=500))

        result = db.get_world_time_map([1, 2, 5])
        assert result == {1: 100, 2: 200, 5: 500}
    finally:
        db.close()


def test_world_time_map_omits_missing_tick_ids(tmp_path) -> None:
    """tick_id 不在 tick_log 中 → 不出现在结果 dict (不抛, 不 default 填)."""
    db = TickDB(str(tmp_path / "ticks.db"))
    try:
        db.insert_tick(_summary(tick=1, world_time=100))
        # request 包含未持久化的 99
        result = db.get_world_time_map([1, 99])
        assert result == {1: 100}
        assert 99 not in result
    finally:
        db.close()


def test_world_time_map_single_tick(tmp_path) -> None:
    """N=1 也走 IN-clause path (placeholder 字符串拼接正确)."""
    db = TickDB(str(tmp_path / "ticks.db"))
    try:
        db.insert_tick(_summary(tick=42, world_time=4200))
        result = db.get_world_time_map([42])
        assert result == {42: 4200}
    finally:
        db.close()


def test_world_time_map_with_duplicate_input(tmp_path) -> None:
    """输入含重复 tick_id 不报错, 结果 dict 因 key 唯一自然去重."""
    db = TickDB(str(tmp_path / "ticks.db"))
    try:
        db.insert_tick(_summary(tick=7, world_time=70))
        result = db.get_world_time_map([7, 7, 7])
        assert result == {7: 70}
    finally:
        db.close()
