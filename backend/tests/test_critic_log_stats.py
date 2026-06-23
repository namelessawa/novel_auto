"""GET /api/tick/critic-log/stats — Phase 6-C iter#7 aggregated stats.

Dashboard-focused 聚合 endpoint, 复用 iter#5 critic_log.jsonl 数据基础.
锁住:

* empty 文件 → 空聚合 (不 500)
* action_distribution 计数正确
* top_codes 按频次降序, 上限 10
* empty_decision_ticks (无 surviving codes 的 tick) 计数
* range 过滤生效
* malformed 行 skip
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import tick_routes
from api.tick_routes import router
from memory.tick_state import TickState
from memory_system.models import WorldState


class _StubRuntime:
    def __init__(self, tick_state):
        self.tick_state = tick_state
        self.orchestrator = None
        self.tick_db = None


def _write_log(data_dir: str, rows: list[dict]) -> None:
    os.makedirs(data_dir, exist_ok=True)
    log_path = os.path.join(data_dir, "critic_log.jsonl")
    with open(log_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    data_dir = str(tmp_path / "novel")
    os.makedirs(data_dir, exist_ok=True)
    ts = TickState(data_dir=data_dir)
    ts.set_world_state(WorldState())
    for _ in range(20):
        ts.advance_tick()
    stub_rt = _StubRuntime(tick_state=ts)
    app.dependency_overrides[tick_routes._resolve_runtime] = lambda: stub_rt
    yield TestClient(app), data_dir
    app.dependency_overrides.clear()


def test_stats_endpoint_empty_file_returns_zero(client) -> None:
    c, _data_dir = client
    r = c.get("/api/tick/critic-log/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["action_distribution"] == {}
    assert body["top_codes"] == []
    assert body["ticks_scanned"] == 0
    assert body["empty_decision_ticks"] == 0


def test_stats_endpoint_action_distribution(client) -> None:
    c, data_dir = client
    rows = [
        {"tick": 1, "action": "ACCEPT", "surviving_codes": []},
        {"tick": 2, "action": "ACCEPT", "surviving_codes": []},
        {"tick": 3, "action": "REVISE", "surviving_codes": ["A1"]},
        {"tick": 4, "action": "REWRITE", "surviving_codes": ["A4", "A6"]},
    ]
    _write_log(data_dir, rows)

    r = c.get("/api/tick/critic-log/stats")
    body = r.json()
    assert body["action_distribution"] == {
        "ACCEPT": 2,
        "REVISE": 1,
        "REWRITE": 1,
    }
    assert body["ticks_scanned"] == 4


def test_stats_endpoint_top_codes_sorted_by_freq(client) -> None:
    c, data_dir = client
    rows = [
        {"tick": 1, "action": "REVISE", "surviving_codes": ["A1", "A1", "D2"]},
        {"tick": 2, "action": "REVISE", "surviving_codes": ["A1", "D2"]},
        {"tick": 3, "action": "REWRITE", "surviving_codes": ["A4"]},
    ]
    # 注意 row 内 surviving_codes 是 per-tick dedup 后的, 此处保留重复模拟
    # 跨 tick 累计. 实际生产 surviving_codes 每 tick 已 dedup.
    _write_log(data_dir, rows)

    r = c.get("/api/tick/critic-log/stats")
    body = r.json()
    codes = body["top_codes"]
    # A1 总数 3 (2+1), D2 2 (1+1), A4 1
    assert codes[0] == {"code": "A1", "count": 3}
    assert codes[1] == {"code": "D2", "count": 2}
    assert codes[2] == {"code": "A4", "count": 1}


def test_stats_endpoint_empty_decision_ticks(client) -> None:
    """surviving_codes=[] 的 tick 计入 empty_decision_ticks."""
    c, data_dir = client
    rows = [
        {"tick": 1, "action": "ACCEPT", "surviving_codes": []},
        {"tick": 2, "action": "ACCEPT", "surviving_codes": []},
        {"tick": 3, "action": "REVISE", "surviving_codes": ["A1"]},
    ]
    _write_log(data_dir, rows)
    body = c.get("/api/tick/critic-log/stats").json()
    assert body["empty_decision_ticks"] == 2


def test_stats_endpoint_range_filter(client) -> None:
    c, data_dir = client
    rows = [
        {"tick": t, "action": "ACCEPT", "surviving_codes": []}
        for t in range(1, 11)
    ]
    _write_log(data_dir, rows)

    r = c.get("/api/tick/critic-log/stats", params={"start_tick": 3, "end_tick": 7})
    body = r.json()
    assert body["ticks_scanned"] == 5  # ticks 3..7


def test_stats_endpoint_top_codes_capped_at_10(client) -> None:
    """超过 10 个 code → top_codes 截 top-10."""
    c, data_dir = client
    # 15 不同 codes, 频次降序
    rows = [
        {
            "tick": 1,
            "action": "REVISE",
            "surviving_codes": [f"X{i}" for i in range(15) for _ in range(15 - i)],
        }
    ]
    _write_log(data_dir, rows)
    body = c.get("/api/tick/critic-log/stats").json()
    assert len(body["top_codes"]) == 10
    # 最高频是 X0 (15 次)
    assert body["top_codes"][0]["code"] == "X0"


def test_stats_endpoint_skips_malformed(client) -> None:
    c, data_dir = client
    log_path = os.path.join(data_dir, "critic_log.jsonl")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write('{"tick": 1, "action": "ACCEPT", "surviving_codes": []}\n')
        f.write('garbage line\n')
        f.write('{"tick": 2, "action": "REVISE", "surviving_codes": ["A1"]}\n')

    body = c.get("/api/tick/critic-log/stats").json()
    assert body["ticks_scanned"] == 2
    assert body["action_distribution"] == {"ACCEPT": 1, "REVISE": 1}
