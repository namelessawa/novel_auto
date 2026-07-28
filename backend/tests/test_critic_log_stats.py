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
    with TestClient(app) as test_client:
        yield test_client, data_dir
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


# ---------------------------------------------------------------------------
# Phase 6-C iter#B — window=N sliding window
# ---------------------------------------------------------------------------


def test_stats_endpoint_window_keeps_last_n(client) -> None:
    """window=N → 只统计最近 N 个 tick (按 jsonl 末尾 N 行)."""
    c, data_dir = client
    rows = [
        {"tick": t, "action": "ACCEPT", "surviving_codes": []} for t in range(1, 21)
    ]
    _write_log(data_dir, rows)

    body = c.get("/api/tick/critic-log/stats", params={"window": 5}).json()
    assert body["ticks_scanned"] == 5
    assert body["window"] == 5


def test_stats_endpoint_window_zero_means_unlimited(client) -> None:
    """window=0 (默认) → 不限, 与无 window 等价."""
    c, data_dir = client
    rows = [
        {"tick": t, "action": "ACCEPT", "surviving_codes": []} for t in range(1, 11)
    ]
    _write_log(data_dir, rows)

    body = c.get("/api/tick/critic-log/stats", params={"window": 0}).json()
    assert body["ticks_scanned"] == 10


def test_stats_endpoint_window_composes_with_range(client) -> None:
    """window + range 同时给 → 先 range 过滤再取末 N. 顺序锁定."""
    c, data_dir = client
    rows = [
        {"tick": t, "action": "REVISE", "surviving_codes": ["A1"]}
        for t in range(1, 21)
    ]
    _write_log(data_dir, rows)

    body = c.get(
        "/api/tick/critic-log/stats",
        params={"start_tick": 5, "end_tick": 15, "window": 3},
    ).json()
    # range 给出 5..15 共 11 个 tick, window=3 取末 3 个 (13/14/15)
    assert body["ticks_scanned"] == 3


def test_stats_endpoint_window_aggregates_correctly(client) -> None:
    """window 截断后 action_distribution / top_codes 反映 window 内数据."""
    c, data_dir = client
    rows = [
        {"tick": 1, "action": "ACCEPT", "surviving_codes": []},
        {"tick": 2, "action": "ACCEPT", "surviving_codes": []},
        {"tick": 3, "action": "REVISE", "surviving_codes": ["A1"]},
        {"tick": 4, "action": "REWRITE", "surviving_codes": ["A4"]},
        {"tick": 5, "action": "REVISE", "surviving_codes": ["A1", "D2"]},
    ]
    _write_log(data_dir, rows)

    body = c.get("/api/tick/critic-log/stats", params={"window": 3}).json()
    # 末 3 tick: 3/4/5 = REVISE/REWRITE/REVISE, codes A1/A4/A1+D2
    assert body["action_distribution"] == {"REVISE": 2, "REWRITE": 1}
    codes_map = {c["code"]: c["count"] for c in body["top_codes"]}
    assert codes_map == {"A1": 2, "A4": 1, "D2": 1}
    assert body["ticks_scanned"] == 3


def test_stats_endpoint_window_default_reports_zero(client) -> None:
    """默认 (无 window 参数) → response.window=0 表示未截断."""
    c, data_dir = client
    rows = [{"tick": 1, "action": "ACCEPT", "surviving_codes": []}]
    _write_log(data_dir, rows)

    body = c.get("/api/tick/critic-log/stats").json()
    assert body["window"] == 0
