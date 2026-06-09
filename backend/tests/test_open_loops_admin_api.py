"""POST /api/tick/open-loops 防静默覆盖 (v2.19.3)。

TickState.add_open_loop 实现是 ``self._open_loops[loop.id] = loop`` — 同 id
直接覆盖。POST /open-loops 也未做任何检查, 管理员二次提交同 id 会丢失原 loop
的运行时累积字段 (last_referenced_tick, opened_tick, 累积的 max_age_ticks 等)。

Narrator 已引用过该伏笔 → last_referenced_tick=42, 被管理员手滑覆盖为 0 →
冷线索检测会把这个其实"很新"的伏笔判为"被遗忘", urgency 计算也漂走。

本测试钉死:
* 重复 id 必须 409 (而非 200 静默覆盖)
* DELETE + POST 同 id 仍可工作 (RESTful 替换语义)
* 不同 id 不冲突
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import tick_routes
from api.tick_routes import router, set_orchestrator_dependencies
from memory.tick_state import TickState
from memory_system.models import OpenLoop, WorldState


class _StubRuntime:
    """v2.26 — _resolve_runtime 桩, 仅暴露 tick_state (open-loops 路由只用它)。"""

    def __init__(self, tick_state):
        self.tick_state = tick_state
        self.orchestrator = None  # open-loops 路由不需要


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(WorldState())
    stub_rt = _StubRuntime(tick_state=ts)
    app.dependency_overrides[tick_routes._resolve_runtime] = lambda: stub_rt
    yield TestClient(app), ts
    app.dependency_overrides.clear()


def _loop_payload(loop_id: str = "loop_x", urgency: int = 7) -> dict:
    return {
        "id": loop_id,
        "opened_tick": 5,
        "description": "公主下落不明",
        "urgency": urgency,
        "type": "other",
    }


def test_post_open_loop_first_time_ok(client) -> None:
    c, ts = client
    r = c.post("/api/tick/open-loops", json=_loop_payload())
    assert r.status_code == 200, r.text
    assert ts.get_open_loop_count() == 1


def test_post_open_loop_duplicate_id_returns_409(client) -> None:
    """同 id 第二次 POST 必须 409, 而不是静默覆盖。"""
    c, ts = client
    # 第一次 — 模拟 Narrator 引用过, 累积 last_referenced_tick
    c.post("/api/tick/open-loops", json=_loop_payload("loop_a", urgency=7))
    ts.touch_open_loop("loop_a", tick=42)
    assert ts.get_open_loops()[0].last_referenced_tick == 42

    # 管理员手滑用同 id 再 POST, 携带不同 urgency
    r = c.post(
        "/api/tick/open-loops",
        json=_loop_payload("loop_a", urgency=2),
    )
    assert r.status_code == 409, (
        f"重复 id 应 409 (避免覆盖 last_referenced_tick=42); "
        f"实际 status={r.status_code} body={r.text[:200]}"
    )
    # last_referenced_tick 必须保留 (覆盖被拒)
    assert ts.get_open_loops()[0].last_referenced_tick == 42
    assert ts.get_open_loops()[0].urgency == 7


def test_post_open_loop_delete_then_repost_ok(client) -> None:
    """RESTful 替换路径: 显式 DELETE 后再 POST 同 id 应成功。"""
    c, ts = client
    c.post("/api/tick/open-loops", json=_loop_payload("loop_b", urgency=4))
    r_del = c.delete("/api/tick/open-loops/loop_b")
    assert r_del.status_code == 200
    r_repost = c.post(
        "/api/tick/open-loops", json=_loop_payload("loop_b", urgency=9)
    )
    assert r_repost.status_code == 200, r_repost.text
    assert ts.get_open_loops()[0].urgency == 9


def test_post_open_loop_distinct_ids_independent(client) -> None:
    c, ts = client
    c.post("/api/tick/open-loops", json=_loop_payload("loop_c"))
    c.post("/api/tick/open-loops", json=_loop_payload("loop_d"))
    assert ts.get_open_loop_count() == 2
