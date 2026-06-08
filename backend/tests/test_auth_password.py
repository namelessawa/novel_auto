"""v2.26 — bcrypt password hash/verify."""

from __future__ import annotations

import pytest

from auth.password import hash_password, verify_password


def test_hash_then_verify_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("secret123")
    assert verify_password("wrong", h) is False


def test_hash_includes_random_salt():
    """同输入两次 hash 应得不同值 (随机 salt)。"""
    a = hash_password("samepw1234")
    b = hash_password("samepw1234")
    assert a != b
    assert verify_password("samepw1234", a)
    assert verify_password("samepw1234", b)


def test_verify_empty_hash_returns_false():
    assert verify_password("anything", "") is False


def test_verify_malformed_hash_returns_false():
    """passlib 内部抛异常时 verify_password 吞掉返回 False, 不让调用方 500。"""
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


def test_password_too_long_rejected():
    """bcrypt 72 字节限制 — 中文 24 字以上拒绝。"""
    long_pw = "啊" * 25  # 25 * 3 = 75 bytes > 72
    with pytest.raises(ValueError, match="bcrypt 限制"):
        hash_password(long_pw)


def test_password_at_72_byte_boundary_ok():
    """边界: 正好 72 字节应能 hash。"""
    pw = "a" * 72
    h = hash_password(pw)
    assert verify_password(pw, h)
