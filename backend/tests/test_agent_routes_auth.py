"""v2.37 — GET /api/agents 不再无认证暴露 agent 注册表 (含 module_path)。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth.dependencies as auth_deps
from api.agent_routes import router
from auth import get_current_user
from auth.config import AuthConfig
from auth.models import User


def _fake_user() -> User:
    return User(
        id="u1",
        email="u1@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    yield a
    a.dependency_overrides.clear()


def test_list_agents_requires_auth(app, monkeypatch) -> None:
    """无 Authorization → 401 (auth.enabled=true 时)。"""
    monkeypatch.setattr(
        auth_deps, "get_auth_config", lambda: AuthConfig(enabled=True)
    )
    r = TestClient(app).get("/api/agents")
    assert r.status_code == 401


def test_list_agents_ok_when_logged_in(app) -> None:
    app.dependency_overrides[get_current_user] = _fake_user
    r = TestClient(app).get("/api/agents")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 9
    assert all("id" in a for a in body["agents"])
