"""TickDB INSERT OR IGNORE 防覆盖 (v2.21)。

回归 P1:此前 events / tick_log 都用 INSERT OR REPLACE, LLM 复用 event_id 或
Orchestrator 重入时, 旧记录被静默覆盖 → Showrunner/NoveltyCritic 的"最近 N
tick 事件分布"统计基于污染后的数据, 趋势判断失真。

新行为:重复 id 跳过、保留首次记录, 仅 WARN 日志。
"""

from __future__ import annotations

import pytest

from memory_system.models import Event, TickSummary
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


def _event(eid: str, tick: int, description: str, nvalue: int = 5) -> Event:
    return Event(
        id=eid,
        tick=tick,
        type="dramatic",
        location="room",
        participants=["a"],
        description=description,
        visible_to=["a"],
        narrative_value=nvalue,
    )


def test_duplicate_event_id_kept_original(tmp_path) -> None:
    db = TickDB(str(tmp_path / "ticks.db"))
    e1 = _event("evt_x", tick=1, description="original", nvalue=8)
    e2 = _event("evt_x", tick=2, description="REPLAY", nvalue=1)

    db.insert_tick(_summary(1), events=[e1])
    db.insert_tick(_summary(2), events=[e2])

    row = db._conn.execute(
        "SELECT tick_id, description, narrative_value FROM events WHERE event_id = ?",
        ("evt_x",),
    ).fetchone()
    assert row is not None
    assert row["tick_id"] == 1
    assert row["description"] == "original"
    assert row["narrative_value"] == 8
    db.close()


def test_duplicate_tick_id_kept_original(tmp_path) -> None:
    db = TickDB(str(tmp_path / "ticks.db"))
    db.insert_tick(_summary(5, world_time=100))
    db.insert_tick(_summary(5, world_time=999))  # 重放, 应被忽略

    row = db._conn.execute(
        "SELECT world_time FROM tick_log WHERE tick_id = ?", (5,)
    ).fetchone()
    assert row["world_time"] == 100
    db.close()


def test_distinct_events_all_inserted(tmp_path) -> None:
    """正向路径:不同 id 都成功写入, 不受新策略影响。"""
    db = TickDB(str(tmp_path / "ticks.db"))
    evts = [_event(f"evt_{i}", tick=1, description=f"d{i}") for i in range(5)]
    db.insert_tick(_summary(1), events=evts)

    count = db._conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
    assert count == 5
    db.close()


def test_duplicate_within_batch_skipped(tmp_path) -> None:
    """同一 batch 内 event id 重复:第二条被忽略, 第一条保留。"""
    db = TickDB(str(tmp_path / "ticks.db"))
    evts = [
        _event("dup", tick=1, description="first"),
        _event("dup", tick=1, description="second"),
        _event("uniq", tick=1, description="other"),
    ]
    db.insert_tick(_summary(1), events=evts)

    row = db._conn.execute(
        "SELECT description FROM events WHERE event_id = ?", ("dup",)
    ).fetchone()
    assert row["description"] == "first"
    total = db._conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"]
    assert total == 2
    db.close()
