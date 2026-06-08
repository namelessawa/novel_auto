"""v2.26 — JWT encode / decode / sliding expiry."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from auth.config import AuthConfig
from auth.jwt_utils import TokenError, decode_token, encode_token, is_near_expiry


@pytest.fixture
def fixed_config(monkeypatch):
    cfg = AuthConfig(
        enabled=True,
        jwt_secret="x" * 64,
        jwt_algorithm="HS256",
        jwt_ttl_days=7,
    )
    monkeypatch.setattr("auth.jwt_utils.get_auth_config", lambda: cfg)
    return cfg


def test_encode_decode_roundtrip(fixed_config):
    token = encode_token("user_abc", "a@b.com")
    payload = decode_token(token)
    assert payload["sub"] == "user_abc"
    assert payload["email"] == "a@b.com"
    assert "iat" in payload
    assert "exp" in payload


def test_decode_invalid_token_raises(fixed_config):
    with pytest.raises(TokenError):
        decode_token("not.a.valid.token")


def test_decode_tampered_token_raises(fixed_config):
    token = encode_token("user_abc", "a@b.com")
    # 改 payload 后签名失配
    parts = token.split(".")
    tampered = parts[0] + "." + parts[1][:-2] + "AA" + "." + parts[2]
    with pytest.raises(TokenError):
        decode_token(tampered)


def test_decode_wrong_secret_raises(monkeypatch):
    cfg_a = AuthConfig(jwt_secret="secret-A" + "x" * 56)
    cfg_b = AuthConfig(jwt_secret="secret-B" + "x" * 56)

    monkeypatch.setattr("auth.jwt_utils.get_auth_config", lambda: cfg_a)
    token = encode_token("u", "e@x.com")
    monkeypatch.setattr("auth.jwt_utils.get_auth_config", lambda: cfg_b)
    with pytest.raises(TokenError):
        decode_token(token)


def test_is_near_expiry_true_within_threshold():
    # exp = now + 12h, threshold 1d → 应该判定 near
    now = datetime.now(timezone.utc)
    exp = int((now + timedelta(hours=12)).timestamp())
    assert is_near_expiry({"exp": exp}, threshold_days=1)


def test_is_near_expiry_false_when_far_out():
    # exp = now + 5d, threshold 1d → 不 near
    now = datetime.now(timezone.utc)
    exp = int((now + timedelta(days=5)).timestamp())
    assert not is_near_expiry({"exp": exp}, threshold_days=1)


def test_is_near_expiry_missing_exp_returns_false():
    assert is_near_expiry({}) is False
    assert is_near_expiry({"exp": "not-a-number"}) is False
