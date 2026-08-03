from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from auth.dependencies import get_current_user


def test_missing_application_jwt_has_structured_auth_code(monkeypatch) -> None:
    monkeypatch.setattr(
        "auth.dependencies.get_auth_config",
        lambda: type("Config", (), {"enabled": True})(),
    )
    app = FastAPI()

    @app.get("/protected")
    def protected(_user=Depends(get_current_user)):
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/protected")

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "AUTH_REQUIRED",
        "message": "未登录",
        "details": {},
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_application_jwt_has_structured_auth_code(monkeypatch) -> None:
    monkeypatch.setattr(
        "auth.dependencies.get_auth_config",
        lambda: type("Config", (), {"enabled": True})(),
    )
    app = FastAPI()

    @app.get("/protected")
    def protected(_user=Depends(get_current_user)):
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer definitely-not-a-jwt"},
        )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_TOKEN_INVALID"
    assert "Provider" not in response.text
