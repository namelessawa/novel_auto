"""Phase 6-B iter#L — /api/tick/narratives 分页.

接 iter#F. 长程小说 >2000 tick 时一次拉全本撑爆 (前端) / 浪费 (后端). 加
page / per_page 参数, reader 连读模式滚到底动态加载.

锁定:
* per_page=0 (默认) → 不分页, 与 iter#F 老行为一致
* per_page=N + page=1 → 切第一页
* page=2 → 切第二页 (offset = (page-1)*per_page)
* page 超出 → 空 narratives + has_more=False, 不抛
* 响应字段: page / per_page / total / has_more
* total = 范围内全部条数 (不受 per_page 影响)
"""

from __future__ import annotations

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


def _write_narratives(data_dir: str, count: int) -> None:
    narratives_dir = os.path.join(data_dir, "narratives")
    os.makedirs(narratives_dir, exist_ok=True)
    for tick in range(1, count + 1):
        path = os.path.join(narratives_dir, f"tick_{tick:06d}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"narrative for tick {tick}")


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    data_dir = str(tmp_path / "novel")
    os.makedirs(data_dir, exist_ok=True)
    ts = TickState(data_dir=data_dir)
    ts.set_world_state(WorldState())
    # Advance 30 ticks so /narratives endpoint sees them.
    for _ in range(30):
        ts.advance_tick()
    db = TickDB(str(tmp_path / "ticks.db"))
    stub_rt = _StubRuntime(tick_state=ts, tick_db=db)
    app.dependency_overrides[tick_routes._resolve_runtime] = lambda: stub_rt
    with TestClient(app) as test_client:
        yield test_client, data_dir
    app.dependency_overrides.clear()
    db.close()


def test_no_pagination_when_per_page_zero(client) -> None:
    """老 contract 兼容: per_page=0 → 拿全部 (与 iter#F 相同)."""
    c, data_dir = client
    _write_narratives(data_dir, 15)
    body = c.get("/api/tick/narratives").json()
    assert body["count"] == 15
    assert len(body["narratives"]) == 15
    assert body["per_page"] == 15  # echoes total when per_page=0
    assert body["page"] == 1
    assert body["total"] == 15
    assert body["has_more"] is False


def test_page_1_returns_first_per_page(client) -> None:
    c, data_dir = client
    _write_narratives(data_dir, 25)
    body = c.get("/api/tick/narratives", params={"per_page": 10, "page": 1}).json()
    assert body["count"] == 10
    assert [n["tick"] for n in body["narratives"]] == list(range(1, 11))
    assert body["page"] == 1
    assert body["per_page"] == 10
    assert body["total"] == 25
    assert body["has_more"] is True


def test_page_2_returns_next_per_page(client) -> None:
    c, data_dir = client
    _write_narratives(data_dir, 25)
    body = c.get("/api/tick/narratives", params={"per_page": 10, "page": 2}).json()
    assert body["count"] == 10
    assert [n["tick"] for n in body["narratives"]] == list(range(11, 21))
    assert body["has_more"] is True


def test_last_page_clamps_to_remaining(client) -> None:
    """page=3 with per_page=10 over 25 narratives → 5 rows + has_more=False."""
    c, data_dir = client
    _write_narratives(data_dir, 25)
    body = c.get("/api/tick/narratives", params={"per_page": 10, "page": 3}).json()
    assert body["count"] == 5
    assert [n["tick"] for n in body["narratives"]] == list(range(21, 26))
    assert body["has_more"] is False


def test_page_out_of_range_returns_empty(client) -> None:
    c, data_dir = client
    _write_narratives(data_dir, 25)
    body = c.get("/api/tick/narratives", params={"per_page": 10, "page": 10}).json()
    assert body["count"] == 0
    assert body["narratives"] == []
    assert body["has_more"] is False
    assert body["total"] == 25


def test_pagination_metadata_in_response(client) -> None:
    """所有响应都带 page / per_page / total / has_more 字段."""
    c, data_dir = client
    _write_narratives(data_dir, 3)
    body = c.get("/api/tick/narratives").json()
    assert "page" in body
    assert "per_page" in body
    assert "total" in body
    assert "has_more" in body


def test_pagination_with_range_filter(client) -> None:
    """range + pagination 协同: 先 range 过滤, 后切页."""
    c, data_dir = client
    _write_narratives(data_dir, 25)
    body = c.get(
        "/api/tick/narratives",
        params={"start_tick": 5, "end_tick": 14, "per_page": 4, "page": 1},
    ).json()
    # range = 10 条 (tick 5-14), per_page=4 → page 1 拿 4 条
    assert body["total"] == 10
    assert body["count"] == 4
    assert [n["tick"] for n in body["narratives"]] == [5, 6, 7, 8]
    assert body["has_more"] is True
