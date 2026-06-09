"""POST /api/tick/inject-event 输入校验 (v2.19.1)。

此前 InjectEventRequest.type 是 plain ``str``, 任何非
EventKind Literal 值都会通过 FastAPI 边界, 直到 Event(type=...) Pydantic
构造时才抛 ValidationError, 用户看到的是 500 而非 422 — 而且 traceback
里有内部模型路径泄露。

类似地, ``visible_to=[]`` 路由 fallback 成 ``["all_in_location"]``, 当 location
也为空时, 事件对所有 CharacterAgent 都不可见, 调用方拿到 200 但事件被静默忽略 —
比 500 更难调试。

本测试钉死三条边界:
1. 非法 type → 422 (而非 500)
2. visible_to 含 all_in_location + location 空 → 422 (而非静默没人看)
3. 显式 id 与 _injected_pending 中已有 id 冲突 → 409 (而非覆盖)

并保留两条 happy-path 不被本次加固破坏。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import tick_routes
from api.tick_routes import router, set_orchestrator_dependencies
from memory.tick_state import TickState
from memory_system.models import Event, TickLocation, WorldState


@dataclass
class _StubOrchestrator:
    """最小 orch 桩 — 满足 inject-event 需要的两个属性。"""

    _injected_pending: list[Event] = field(default_factory=list)
    is_paused: bool = False

    def inject_event(self, event: Event) -> None:
        self._injected_pending.append(event)


class _StubRuntime:
    """v2.26 — _resolve_runtime 期望返回 TickRuntime, 但本测试只需 .orchestrator
    + .tick_state, 用 stub 替代避免 TickRuntime 完整构造 (9 agents + DB)。"""

    def __init__(self, orchestrator, tick_state):
        self.orchestrator = orchestrator
        self.tick_state = tick_state


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(
        WorldState(locations=[TickLocation(id="city", name="都城")])
    )
    orch = _StubOrchestrator()
    # v2.26 — 用 dependency_overrides 绕过 get_current_user + _resolve_runtime
    stub_rt = _StubRuntime(orchestrator=orch, tick_state=ts)
    app.dependency_overrides[tick_routes._resolve_runtime] = lambda: stub_rt
    yield TestClient(app), ts, orch
    app.dependency_overrides.clear()


# ------------------------------------------------------------------
# 1. type 字段必须是 EventKind Literal
# ------------------------------------------------------------------


def test_inject_event_rejects_unknown_type_with_422(client) -> None:
    c, _, _ = client
    r = c.post(
        "/api/tick/inject-event",
        json={"type": "fight", "description": "x", "location": "city"},
    )
    assert r.status_code == 422, (
        f"非法 type 应在请求边界 422 拒绝, 实际 status={r.status_code} "
        f"body={r.text[:200]}"
    )
    # 错误 message 应提到 type 字段
    body = r.json()
    assert "type" in str(body).lower()


def test_inject_event_accepts_valid_type(client) -> None:
    c, _, orch = client
    r = c.post(
        "/api/tick/inject-event",
        json={"type": "dramatic", "description": "雷声大作", "location": "city"},
    )
    assert r.status_code == 200, r.text
    assert len(orch._injected_pending) == 1


# ------------------------------------------------------------------
# 2. visible_to=all_in_location + location 空 → 422
# ------------------------------------------------------------------


def test_inject_event_all_in_location_requires_location(client) -> None:
    """visible_to=all_in_location 配空 location 会让事件对谁都不可见 — 拒绝。"""
    c, _, orch = client
    r = c.post(
        "/api/tick/inject-event",
        json={
            "type": "dramatic",
            "description": "x",
            "location": "",  # 显式空
            "visible_to": ["all_in_location"],
        },
    )
    assert r.status_code == 422, (
        f"空 location + all_in_location 应被拒绝, "
        f"否则事件对所有人不可见而调用方完全感知不到。"
        f"实际 status={r.status_code} body={r.text[:200]}"
    )
    assert orch._injected_pending == []


def test_inject_event_default_visible_to_with_empty_location_rejected(
    client,
) -> None:
    """visible_to 不传 → 路由 fallback 成 all_in_location; 此时空 location 同样无效。"""
    c, _, orch = client
    r = c.post(
        "/api/tick/inject-event",
        json={"type": "dramatic", "description": "x", "location": ""},
    )
    assert r.status_code == 422, (
        f"默认 visible_to + 空 location 同样应拒绝 "
        f"(fallback 后等价于 all_in_location)。实际 status={r.status_code} "
        f"body={r.text[:200]}"
    )
    assert orch._injected_pending == []


def test_inject_event_explicit_visible_to_no_location_ok(client) -> None:
    """visible_to 显式给 character_id 列表, location 可空 (不依赖 location 派发)。"""
    c, _, orch = client
    r = c.post(
        "/api/tick/inject-event",
        json={
            "type": "dramatic",
            "description": "梦中惊醒",
            "location": "",
            "visible_to": ["alice"],
        },
    )
    assert r.status_code == 200, r.text
    assert len(orch._injected_pending) == 1
    assert orch._injected_pending[0].visible_to == ["alice"]


# ------------------------------------------------------------------
# 3. id 冲突 — 跟 _injected_pending 已有项重复 → 409
# ------------------------------------------------------------------


def test_inject_event_duplicate_id_rejected_with_409(client) -> None:
    c, _, orch = client
    payload = {
        "id": "evt_test_dup",
        "type": "dramatic",
        "description": "x",
        "location": "city",
    }
    r1 = c.post("/api/tick/inject-event", json=payload)
    assert r1.status_code == 200
    r2 = c.post("/api/tick/inject-event", json=payload)
    assert r2.status_code == 409, (
        f"显式相同 id 应 409 (避免静默覆盖); 实际 status={r2.status_code} "
        f"body={r2.text[:200]}"
    )
    # _injected_pending 仍只有第一次注入的事件
    assert len(orch._injected_pending) == 1


def test_inject_event_auto_generated_ids_do_not_collide(client) -> None:
    """连续不带 id 注入, 自动生成的 id 必须不同 (避免 evt_user_5_0 重复)。"""
    c, _, orch = client
    payload = {"type": "dramatic", "description": "x", "location": "city"}
    for _ in range(3):
        r = c.post("/api/tick/inject-event", json=payload)
        assert r.status_code == 200, r.text
    ids = {e.id for e in orch._injected_pending}
    assert len(ids) == 3, (
        f"自动 id 必须唯一; 实际拿到 {ids} ({len(orch._injected_pending)} 注入)"
    )


# ------------------------------------------------------------------
# 4. narrative_value 仍然受 0-10 约束 (回归检查)
# ------------------------------------------------------------------


def test_inject_event_narrative_value_out_of_range_422(client) -> None:
    c, _, _ = client
    r = c.post(
        "/api/tick/inject-event",
        json={
            "type": "dramatic",
            "description": "x",
            "location": "city",
            "narrative_value": 99,
        },
    )
    assert r.status_code == 422
