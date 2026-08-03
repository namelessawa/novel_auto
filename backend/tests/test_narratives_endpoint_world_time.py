"""GET /api/tick/narratives — Phase 6-B reader endpoint contract.

v2.48 ship 时 docstring 承诺 ``{tick, world_time, text, char_count}`` 但实
现遗漏 ``world_time``. 本 test 锁住:

* 每行返回 ``world_time``, 取自 TickDB.tick_log
* 缺失 world_time (tick_log 没记录) → 字段为 None, 不抛
* start/end 范围过滤生效
* 空 narratives 目录返回空列表
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import tick_routes
from api.tick_routes import router
from memory.tick_state import TickState
from memory_system.models import TickSummary, WorldState
from persistence.tick_db import TickDB


class _StubRuntime:
    def __init__(self, tick_state, tick_db):
        self.tick_state = tick_state
        self.tick_db = tick_db
        self.orchestrator = None


def _write_narrative(data_dir: str, tick: int, text: str) -> None:
    narratives_dir = os.path.join(data_dir, "narratives")
    os.makedirs(narratives_dir, exist_ok=True)
    path = os.path.join(narratives_dir, f"tick_{tick:06d}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _summary(tick: int, world_time: int) -> TickSummary:
    return TickSummary(
        tick=tick,
        world_time=world_time,
        agents_called=["narrator"],
        events_generated=[],
        narrator_produced_text=True,
        narrator_output_chars=10,
    )


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    data_dir = str(tmp_path / "novel")
    os.makedirs(data_dir, exist_ok=True)
    ts = TickState(data_dir=data_dir)
    ts.set_world_state(WorldState())
    # Advance tick to 5 so /narratives end_tick=0 covers ticks 1..5.
    for _ in range(5):
        ts.advance_tick()
    db = TickDB(str(tmp_path / "ticks.db"))
    stub_rt = _StubRuntime(tick_state=ts, tick_db=db)
    app.dependency_overrides[tick_routes._resolve_runtime] = lambda: stub_rt
    with TestClient(app) as test_client:
        yield test_client, data_dir, db
    app.dependency_overrides.clear()
    db.close()


def test_narratives_endpoint_populates_world_time(client) -> None:
    """每个 narrative row 都带 world_time, 取自 TickDB.tick_log."""
    c, data_dir, db = client
    db.insert_tick(_summary(tick=1, world_time=100))
    db.insert_tick(_summary(tick=3, world_time=300))
    _write_narrative(data_dir, tick=1, text="一段叙述")
    _write_narrative(data_dir, tick=3, text="第二段叙述")

    r = c.get("/api/tick/narratives")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    assert {n["tick"]: n["world_time"] for n in body["narratives"]} == {1: 100, 3: 300}
    # text + char_count 字段保留
    assert all("text" in n and "char_count" in n for n in body["narratives"])


def test_narratives_endpoint_missing_world_time_is_none(client) -> None:
    """narrative 有 .txt 但 TickDB 无 tick_log 记录 → world_time=None, 不抛."""
    c, data_dir, _db = client
    _write_narrative(data_dir, tick=2, text="孤立段落")

    r = c.get("/api/tick/narratives")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    assert body["narratives"][0]["world_time"] is None


def test_narratives_endpoint_respects_start_end_range(client) -> None:
    """start_tick / end_tick 范围过滤生效, world_time 仍正确."""
    c, data_dir, db = client
    for tick, wt in [(1, 100), (2, 200), (3, 300), (4, 400)]:
        db.insert_tick(_summary(tick=tick, world_time=wt))
        _write_narrative(data_dir, tick=tick, text=f"tick {tick}")

    r = c.get("/api/tick/narratives", params={"start_tick": 2, "end_tick": 3})
    assert r.status_code == 200
    body = r.json()
    assert [n["tick"] for n in body["narratives"]] == [2, 3]
    assert [n["world_time"] for n in body["narratives"]] == [200, 300]


def test_narratives_endpoint_empty_dir_returns_empty(client) -> None:
    """无 narratives/ 目录或目录空 → 返回空, 不抛."""
    c, _data_dir, _db = client
    r = c.get("/api/tick/narratives")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["narratives"] == []
