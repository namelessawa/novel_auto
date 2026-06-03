"""Hallucination 诊断 API (v2.18 Phase 9)。

GET /api/tick/diagnostic/hallucination —
返回 TickState.get_hallucination_stats() + 额外的 agent runtime 摘要。

让前端 / 监控可以查"哪个 agent 被 Guardian 建议过降级"。生产数据 N 天后用于
判断是否启用 HALLUCINATION_AUTO_DEGRADE。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import tick_routes
from api.tick_routes import router, set_orchestrator_dependencies
from memory.tick_state import TickState
from memory_system.models import (
    AgentRuntimeState,
    CharacterProfile,
    CharacterState,
    WorldState,
)


@pytest.fixture
def client(tmp_path):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(WorldState())
    ts.upsert_character_profile(
        CharacterProfile(id="elara", name="Elara", importance_tier="A")
    )
    ts.upsert_character_state(CharacterState(character_id="elara"))
    set_orchestrator_dependencies(tick_state=ts)
    yield TestClient(app), ts
    # cleanup — 防 fixture 污染后续测试
    set_orchestrator_dependencies(tick_state=None)
    tick_routes._container.tick_state = None


def test_diagnostic_hallucination_empty(client) -> None:
    """无任何 Guardian 建议时, 返回空 stats + total=0。"""
    c, _ = client
    r = c.get("/api/tick/diagnostic/hallucination")
    assert r.status_code == 200
    body = r.json()
    assert body["stats"] == {}
    assert body["total_agents_flagged"] == 0
    assert body["auto_degrade_active"] is False


def test_diagnostic_hallucination_with_data(client, monkeypatch) -> None:
    c, ts = client
    ts.record_degrade_recommendation(
        agent_id="character_agent:elara", tick=10, hits=3
    )
    ts.record_degrade_recommendation(
        agent_id="character_agent:elara", tick=15, hits=2
    )
    ts.record_degrade_recommendation(
        agent_id="character_agent:zoe", tick=20, hits=1
    )

    monkeypatch.delenv("HALLUCINATION_AUTO_DEGRADE", raising=False)

    r = c.get("/api/tick/diagnostic/hallucination")
    assert r.status_code == 200
    body = r.json()
    assert body["total_agents_flagged"] == 2
    assert body["auto_degrade_active"] is False
    elara = body["stats"]["character_agent:elara"]
    assert elara["degrade_recommendations"] == 2
    assert elara["hallucination_hits"] == 5
    assert elara["last_degrade_recommended_tick"] == 15
    assert elara["model_tier_override_active"] is False


def test_diagnostic_hallucination_auto_degrade_flag(client, monkeypatch) -> None:
    """env HALLUCINATION_AUTO_DEGRADE=1 时应在 body 中标记 active=True。"""
    c, ts = client
    monkeypatch.setenv("HALLUCINATION_AUTO_DEGRADE", "1")
    r = c.get("/api/tick/diagnostic/hallucination")
    assert r.status_code == 200
    assert r.json()["auto_degrade_active"] is True


def test_diagnostic_hallucination_returns_503_when_no_tick_state() -> None:
    """tick_state 未注入时, 路由应返回 503 而不是崩溃。"""
    from fastapi import FastAPI

    tick_routes._container.tick_state = None
    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)
    r = c.get("/api/tick/diagnostic/hallucination")
    assert r.status_code == 503
