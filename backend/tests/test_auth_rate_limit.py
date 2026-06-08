"""v2.26 — Per-scope per-key sliding-window rate limiter."""

from __future__ import annotations

import time

import pytest

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
