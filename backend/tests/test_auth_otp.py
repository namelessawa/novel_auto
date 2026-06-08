"""v2.26 — OTP generate / verify / lockout / TTL."""

from __future__ import annotations

import os
import re
import tempfile
import time

import pytest

import auth.store as store_module
from auth.config import AuthConfig
from auth.otp import (
    MAX_OTP_ATTEMPTS,
    OTPExpired,
    OTPInvalid,
    OTPLockedOut,
    send_otp,
    verify_otp,
)


@pytest.fixture
def temp_store(monkeypatch):
    """每个 test 用独立 sqlite 文件, 避免污染。"""
    td = tempfile.mkdtemp()
    path = os.path.join(td, "auth.db")
    monkeypatch.setattr(store_module, "_DEFAULT_DB_PATH", path)
    s = store_module._reset_for_tests(db_path=path)
    yield s
    store_module._reset_for_tests()  # 还原 default


@pytest.fixture
def fast_otp_config(monkeypatch):
    cfg = AuthConfig(otp_ttl_seconds=300)
    monkeypatch.setattr("auth.otp.get_auth_config", lambda: cfg)
    return cfg


@pytest.fixture
def mock_smtp(monkeypatch):
    """拦截邮件发送, 记录调用。"""
    sent: list[tuple] = []

    async def _send(to_addr, code, purpose="登录"):
        sent.append((to_addr, code, purpose))

    monkeypatch.setattr("auth.otp.send_otp_email", _send)
    return sent


@pytest.mark.asyncio
async def test_send_otp_writes_record_and_emails(
    temp_store, fast_otp_config, mock_smtp
):
    code = await send_otp("user@example.com", "register")
    assert re.match(r"^\d{6}$", code)
    rec = temp_store.get_otp("user@example.com", "register")
    assert rec is not None
    assert rec["attempts"] == 0
    assert rec["expires_at"] > time.time()
    assert len(mock_smtp) == 1
    assert mock_smtp[0][0] == "user@example.com"
    assert mock_smtp[0][1] == code


@pytest.mark.asyncio
async def test_verify_success_consumes_record(
    temp_store, fast_otp_config, mock_smtp
):
    code = await send_otp("x@y.com", "login")
    verify_otp("x@y.com", "login", code)
    # 消费后应被删
    assert temp_store.get_otp("x@y.com", "login") is None


@pytest.mark.asyncio
async def test_verify_wrong_code_increments_attempts(
    temp_store, fast_otp_config, mock_smtp
):
    await send_otp("x@y.com", "login")
    with pytest.raises(OTPInvalid):
        verify_otp("x@y.com", "login", "000000")
    rec = temp_store.get_otp("x@y.com", "login")
    assert rec is not None
    assert rec["attempts"] == 1


@pytest.mark.asyncio
async def test_verify_locks_out_after_max_attempts(
    temp_store, fast_otp_config, mock_smtp
):
    await send_otp("x@y.com", "login")
    # 用错的 code 试 MAX 次
    for _ in range(MAX_OTP_ATTEMPTS):
        with pytest.raises((OTPInvalid, OTPLockedOut)):
            verify_otp("x@y.com", "login", "000000")
    # 第 6 次必锁
    with pytest.raises(OTPLockedOut):
        verify_otp("x@y.com", "login", "000000")


@pytest.mark.asyncio
async def test_verify_expired_raises(
    temp_store, fast_otp_config, mock_smtp, monkeypatch
):
    code = await send_otp("x@y.com", "login")
    # 把过期时间倒推 600s (已过期 5min)
    rec = temp_store.get_otp("x@y.com", "login")
    temp_store.put_otp("x@y.com", "login", rec["otp_hash"], time.time() - 600)

    with pytest.raises(OTPExpired):
        verify_otp("x@y.com", "login", code)
    # 过期记录已被消费
    assert temp_store.get_otp("x@y.com", "login") is None


def test_verify_nonexistent_raises_invalid(temp_store):
    with pytest.raises(OTPInvalid):
        verify_otp("never@sent.com", "login", "123456")


@pytest.mark.asyncio
async def test_new_send_resets_attempts(
    temp_store, fast_otp_config, mock_smtp
):
    code1 = await send_otp("x@y.com", "login")
    with pytest.raises(OTPInvalid):
        verify_otp("x@y.com", "login", "000000")
    rec = temp_store.get_otp("x@y.com", "login")
    assert rec["attempts"] == 1

    # 重发 — attempts 应重置
    code2 = await send_otp("x@y.com", "login")
    assert code1 != code2 or True  # 概率上不同但允许相同
    rec = temp_store.get_otp("x@y.com", "login")
    assert rec["attempts"] == 0


@pytest.mark.asyncio
async def test_smtp_failure_rolls_back_record(
    temp_store, fast_otp_config, monkeypatch
):
    from auth.smtp_client import SMTPError

    async def _failing(*a, **kw):
        raise SMTPError("simulated")

    monkeypatch.setattr("auth.otp.send_otp_email", _failing)

    with pytest.raises(SMTPError):
        await send_otp("x@y.com", "login")
    # 失败后 OTP 应已回滚
    assert temp_store.get_otp("x@y.com", "login") is None
