"""GET /api/tick/critic-log — Phase 6-C iter#6 reader endpoint.

iter#5 让 orchestrator 把 critic decisions append 到
`{data_dir}/critic_log.jsonl`. 本 endpoint 把 jsonl stream 给 frontend,
段落级 quality marker 和长程分析的统一入口.

锁住:
* 空文件 → 空 rows
* 多行 jsonl 完整解析
* start_tick / end_tick 范围过滤生效
* limit 截断生效
* malformed line 跳过, 不抛 500
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
    for _ in range(10):
        ts.advance_tick()
    stub_rt = _StubRuntime(tick_state=ts)
    app.dependency_overrides[tick_routes._resolve_runtime] = lambda: stub_rt
    yield TestClient(app), data_dir
    app.dependency_overrides.clear()


def test_critic_log_endpoint_empty_returns_empty(client) -> None:
    """无 critic_log.jsonl 文件 → 空 rows, 不 500."""
    c, _data_dir = client
    r = c.get("/api/tick/critic-log")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["rows"] == []


def test_critic_log_endpoint_returns_rows(client) -> None:
    """jsonl 多行解析正确, 字段保留."""
    c, data_dir = client
    rows = [
        {"tick": 1, "action": "ACCEPT", "surviving_codes": ["A1"], "decision_trail": []},
        {"tick": 2, "action": "REVISE", "surviving_codes": ["A1", "D2"], "decision_trail": ["round 1"]},
        {"tick": 3, "action": "ACCEPT", "surviving_codes": [], "decision_trail": []},
    ]
    _write_log(data_dir, rows)

    r = c.get("/api/tick/critic-log")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert [row["tick"] for row in body["rows"]] == [1, 2, 3]
    assert body["rows"][1]["action"] == "REVISE"
    assert body["rows"][1]["surviving_codes"] == ["A1", "D2"]


def test_critic_log_endpoint_filters_by_range(client) -> None:
    """start_tick / end_tick 过滤生效."""
    c, data_dir = client
    rows = [
        {"tick": t, "action": "ACCEPT", "surviving_codes": [], "decision_trail": []}
        for t in range(1, 6)
    ]
    _write_log(data_dir, rows)

    r = c.get("/api/tick/critic-log", params={"start_tick": 2, "end_tick": 4})
    body = r.json()
    assert [row["tick"] for row in body["rows"]] == [2, 3, 4]


def test_critic_log_endpoint_limit_truncates(client) -> None:
    """limit 截断生效, truncated 字段返回 true."""
    c, data_dir = client
    rows = [
        {"tick": t, "action": "ACCEPT", "surviving_codes": [], "decision_trail": []}
        for t in range(1, 11)
    ]
    _write_log(data_dir, rows)

    r = c.get("/api/tick/critic-log", params={"limit": 3})
    body = r.json()
    assert body["count"] == 3
    assert body["truncated"] is True


def test_critic_log_endpoint_skips_malformed_lines(client, caplog) -> None:
    """malformed JSON 行 skip + warn, 端点不抛 500."""
    c, data_dir = client
    log_path = os.path.join(data_dir, "critic_log.jsonl")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write('{"tick": 1, "action": "ACCEPT"}\n')
        f.write('this is not json\n')
        f.write('{"tick": 3, "action": "REVISE"}\n')

    r = c.get("/api/tick/critic-log")
    assert r.status_code == 200
    body = r.json()
    # malformed line 跳过, 有效 2 行保留
    ticks = [row["tick"] for row in body["rows"]]
    assert ticks == [1, 3]


def test_critic_log_endpoint_unicode_safe(client) -> None:
    """中文 evidence + ensure_ascii=False 不破 endpoint."""
    c, data_dir = client
    rows = [{
        "tick": 1,
        "action": "REWRITE",
        "surviving_codes": ["A4"],
        "decision_trail": ["round 1: 仿佛 触发 → REWRITE"],
    }]
    _write_log(data_dir, rows)

    r = c.get("/api/tick/critic-log")
    body = r.json()
    assert "仿佛" in body["rows"][0]["decision_trail"][0]
