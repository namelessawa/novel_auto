"""v2.26 — Per-scope per-key sliding-window rate limiter.

v2.37 — 追加 get_client_ip 测试: 限流按 IP 记账, 直连部署下 X-Forwarded-For /
CF-Connecting-IP 可被客户端伪造来绕过限流; 仅 auth.trusted_proxy=true 才信代理头。
"""

from __future__ import annotations

import time

import pytest
from starlette.requests import Request

import auth.dependencies as auth_deps
from auth.config import AuthConfig
from auth.dependencies import get_client_ip
from auth.rate_limit import RateLimit, RateLimiter


def test_under_limit_allows_all():
    rl = RateLimiter()
    limit = RateLimit(3, 60)
    assert rl.check_and_record("scope", "ip-1", limit)
    assert rl.check_and_record("scope", "ip-1", limit)
    assert rl.check_and_record("scope", "ip-1", limit)


def test_at_limit_blocks_next():
    rl = RateLimiter()
    limit = RateLimit(3, 60)
    for _ in range(3):
        rl.check_and_record("s", "k", limit)
    assert not rl.check_and_record("s", "k", limit)


def test_different_scopes_independent():
    rl = RateLimiter()
    limit = RateLimit(1, 60)
    assert rl.check_and_record("scope_a", "same-key", limit)
    assert rl.check_and_record("scope_b", "same-key", limit)
    # 同 scope 同 key 上限
    assert not rl.check_and_record("scope_a", "same-key", limit)


def test_different_keys_independent():
    rl = RateLimiter()
    limit = RateLimit(1, 60)
    assert rl.check_and_record("s", "alice", limit)
    assert rl.check_and_record("s", "bob", limit)
    assert not rl.check_and_record("s", "alice", limit)


def test_window_expiry_releases_slot(monkeypatch):
    rl = RateLimiter()
    limit = RateLimit(1, 60)
    now = [1_000_000.0]
    monkeypatch.setattr("auth.rate_limit.time.time", lambda: now[0])

    assert rl.check_and_record("s", "k", limit)
    assert not rl.check_and_record("s", "k", limit)
    # 61s 后窗口外
    now[0] += 61
    assert rl.check_and_record("s", "k", limit)


def test_zero_max_count_always_blocks():
    rl = RateLimiter()
    limit = RateLimit(0, 60)
    assert not rl.check_and_record("s", "k", limit)


def test_reset_clears_state():
    rl = RateLimiter()
    limit = RateLimit(1, 60)
    rl.check_and_record("s", "k", limit)
    assert not rl.check_and_record("s", "k", limit)
    rl.reset()
    assert rl.check_and_record("s", "k", limit)


# ---- get_client_ip — 代理头伪造防御 (v2.37) ---------------------------------


def _make_request(
    headers: dict[str, str] | None = None, client_host: str = "9.9.9.9"
) -> Request:
    headers = headers or {}
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in headers.items()
        ],
        "client": (client_host, 12345),
    }
    return Request(scope)


def _set_cfg(monkeypatch, *, trusted_proxy: bool) -> None:
    monkeypatch.setattr(
        auth_deps,
        "get_auth_config",
        lambda: AuthConfig(trusted_proxy=trusted_proxy),
    )


def test_direct_deploy_ignores_spoofed_forward_headers(monkeypatch):
    """trusted_proxy=False (默认): 伪造的 XFF / CF 头不得改变限流 key。"""
    _set_cfg(monkeypatch, trusted_proxy=False)
    req = _make_request(
        headers={
            "X-Forwarded-For": "1.2.3.4",
            "CF-Connecting-IP": "5.6.7.8",
        },
        client_host="9.9.9.9",
    )
    assert get_client_ip(req) == "9.9.9.9"


def test_direct_deploy_uses_client_host(monkeypatch):
    _set_cfg(monkeypatch, trusted_proxy=False)
    assert get_client_ip(_make_request(client_host="10.0.0.7")) == "10.0.0.7"


def test_trusted_proxy_prefers_cf_connecting_ip(monkeypatch):
    _set_cfg(monkeypatch, trusted_proxy=True)
    req = _make_request(
        headers={
            "CF-Connecting-IP": "5.6.7.8",
            "X-Forwarded-For": "1.2.3.4, 2.2.2.2",
        }
    )
    assert get_client_ip(req) == "5.6.7.8"


def test_trusted_proxy_falls_back_to_first_xff(monkeypatch):
    _set_cfg(monkeypatch, trusted_proxy=True)
    req = _make_request(headers={"X-Forwarded-For": "1.2.3.4, 2.2.2.2"})
    assert get_client_ip(req) == "1.2.3.4"


def test_trusted_proxy_without_headers_uses_client_host(monkeypatch):
    _set_cfg(monkeypatch, trusted_proxy=True)
    assert get_client_ip(_make_request(client_host="172.16.0.9")) == "172.16.0.9"
