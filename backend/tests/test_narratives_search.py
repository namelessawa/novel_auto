"""Phase 6 iter#AAA — GET /api/tick/narratives/search.

跨 narratives/*.txt grep, 返回 matching narratives.

锁定:
* q 命中 → 返回包含 q 的 narrative 列表
* snippet 给 q 周围 ±40 chars 上下文
* viewpoint_character_id 来自 sidecar (iter#F)
* range filter (start_tick / end_tick) 生效
* 空 q → 400 error
* 0 命中 → 空 results
* 大小写敏感 (中文不区分 — Chinese has no case, but English keywords lower)
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
from persistence.tick_db import TickDB


class _StubRuntime:
    def __init__(self, tick_state, tick_db):
        self.tick_state = tick_state
        self.tick_db = tick_db
        self.orchestrator = None


def _write_narrative(
    data_dir: str, tick: int, text: str, *, viewpoint: str | None = None
) -> None:
    narratives_dir = os.path.join(data_dir, "narratives")
    os.makedirs(narratives_dir, exist_ok=True)
    txt_path = os.path.join(narratives_dir, f"tick_{tick:06d}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    if viewpoint:
        meta_path = os.path.join(narratives_dir, f"tick_{tick:06d}.meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"viewpoint_character_id": viewpoint}, f, ensure_ascii=False)


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
    db = TickDB(str(tmp_path / "ticks.db"))
    stub_rt = _StubRuntime(tick_state=ts, tick_db=db)
    app.dependency_overrides[tick_routes._resolve_runtime] = lambda: stub_rt
    with TestClient(app) as test_client:
        yield test_client, data_dir
    app.dependency_overrides.clear()
    db.close()


# ---------------------------------------------------------------------------
# Basic hits
# ---------------------------------------------------------------------------


def test_search_finds_matching_narratives(client) -> None:
    c, data_dir = client
    _write_narrative(data_dir, 1, "苏默走进档案馆, 守备官递来卷宗.", viewpoint="char_su_mo")
    _write_narrative(data_dir, 2, "他翻开第一页, 字迹潦草难辨.")
    _write_narrative(data_dir, 3, "档案馆里灯光昏暗, 苏默环顾四周.")

    body = c.get("/api/tick/narratives/search", params={"q": "档案馆"}).json()
    assert body["count"] == 2
    matched_ticks = sorted(n["tick"] for n in body["results"])
    assert matched_ticks == [1, 3]


def test_search_returns_snippet_with_context(client) -> None:
    c, data_dir = client
    text = "苏默走进档案馆, 守备官递来卷宗, 他点头收下, 塞进布袋."
    _write_narrative(data_dir, 1, text)
    body = c.get("/api/tick/narratives/search", params={"q": "守备官"}).json()
    row = body["results"][0]
    assert "snippet" in row
    assert "守备官" in row["snippet"]


def test_search_includes_viewpoint(client) -> None:
    c, data_dir = client
    _write_narrative(data_dir, 1, "苏默走进档案馆.", viewpoint="char_su_mo")
    body = c.get("/api/tick/narratives/search", params={"q": "档案馆"}).json()
    assert body["results"][0]["viewpoint_character_id"] == "char_su_mo"


def test_search_missing_sidecar_returns_none_viewpoint(client) -> None:
    c, data_dir = client
    _write_narrative(data_dir, 1, "档案馆.")
    body = c.get("/api/tick/narratives/search", params={"q": "档案馆"}).json()
    assert body["results"][0]["viewpoint_character_id"] is None


# ---------------------------------------------------------------------------
# No hits
# ---------------------------------------------------------------------------


def test_search_no_hits_returns_empty(client) -> None:
    c, data_dir = client
    _write_narrative(data_dir, 1, "苏默走进档案馆.")
    body = c.get("/api/tick/narratives/search", params={"q": "炼金"}).json()
    assert body["count"] == 0
    assert body["results"] == []


# ---------------------------------------------------------------------------
# Range filter
# ---------------------------------------------------------------------------


def test_search_range_filter(client) -> None:
    c, data_dir = client
    for tick in range(1, 11):
        _write_narrative(data_dir, tick, f"苏默走过第 {tick} 段路.")
    body = c.get(
        "/api/tick/narratives/search",
        params={"q": "走过", "start_tick": 4, "end_tick": 7},
    ).json()
    assert body["count"] == 4
    assert sorted(n["tick"] for n in body["results"]) == [4, 5, 6, 7]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_search_empty_q_returns_400(client) -> None:
    c, _ = client
    r = c.get("/api/tick/narratives/search", params={"q": ""})
    assert r.status_code == 400


def test_search_q_with_special_chars(client) -> None:
    """搜索内容含正则 metachar (?, ., *) 应当作 literal 处理."""
    c, data_dir = client
    _write_narrative(data_dir, 1, "卷宗编号 6-17 (优先级 A) — 待处理.")
    body = c.get(
        "/api/tick/narratives/search", params={"q": "(优先级 A)"}
    ).json()
    assert body["count"] == 1


def test_search_limit_respected(client) -> None:
    c, data_dir = client
    for tick in range(1, 21):
        _write_narrative(data_dir, tick, f"档案馆 {tick}.")
    body = c.get(
        "/api/tick/narratives/search", params={"q": "档案馆", "limit": 5}
    ).json()
    assert body["count"] == 5
    assert body["truncated"] is True


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


def test_search_response_schema(client) -> None:
    c, data_dir = client
    _write_narrative(data_dir, 1, "档案馆里灯光昏暗.")
    body = c.get("/api/tick/narratives/search", params={"q": "档案馆"}).json()
    assert "count" in body
    assert "results" in body
    assert "q" in body
    assert "truncated" in body
    if body["results"]:
        row = body["results"][0]
        assert "tick" in row
        assert "char_count" in row
        assert "snippet" in row
        assert "viewpoint_character_id" in row
