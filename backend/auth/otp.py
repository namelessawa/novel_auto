"""OTP 生成 / 校验 — 6 位数字, 5 分钟 TTL, 5 次尝试上限。

为何 hash 存储而非明文: 即使 auth.db 泄露, OTP 也无法被还原 (有效期 5 分钟,
攻击者也无法用泄露的 hash 直接登录)。这是过度防御, 但成本很低。

为何 5 次尝试: 6 位数字空间 10^6, 期望 5 万次猜对; 5 次给手抖友好。
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time

from .config import get_auth_config
from .smtp_client import SMTPError, send_otp_email
from .store import get_user_store

logger = logging.getLogger(__name__)

MAX_OTP_ATTEMPTS = 5


class OTPError(Exception):
    pass


class OTPInvalid(OTPError):
    pass


class OTPExpired(OTPError):
    pass


class OTPLockedOut(OTPError):
    pass


def _generate_code() -> str:
    """6 位均匀分布数字 — secrets.randbelow 避免低位偏。"""
    return f"{secrets.randbelow(1000000):06d}"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _constant_time_eq(a: str, b: str) -> bool:
    return secrets.compare_digest(a, b)


async def send_otp(email: str, purpose: str) -> str:
    """生成 + 持久化 + 邮件投递。返回明文 code (测试用; 生产不要 log)。"""
    cfg = get_auth_config()
    code = _generate_code()
    expires_at = time.time() + cfg.otp_ttl_seconds
    store = get_user_store()
    store.put_otp(email.lower(), purpose, _hash_code(code), expires_at)
    try:
        await send_otp_email(email, code, purpose=_purpose_label(purpose))
    except SMTPError:
        # SMTP 失败回滚 — 否则用户点不到验证码却已计入 send 限流
        store.delete_otp(email.lower(), purpose)
        raise
    return code


def verify_otp(email: str, purpose: str, code: str) -> None:
    """成功 → 消费 OTP 并返回 None;
    失败 → 抛 OTPInvalid / OTPExpired / OTPLockedOut。

    所有失败路径都不暴露 OTP 是否存在 — 错误消息文案区分但不泄露存在性。
    """
    store = get_user_store()
    rec = store.get_otp(email, purpose)
    if rec is None:
        raise OTPInvalid("验证码错误或已过期")

    if rec["attempts"] >= MAX_OTP_ATTEMPTS:
        # 锁死: 必须重新 send 才能再试
        raise OTPLockedOut("尝试次数过多, 请重新获取验证码")

    if rec["expires_at"] < time.time():
        store.delete_otp(email, purpose)
        raise OTPExpired("验证码已过期, 请重新获取")

    if not _constant_time_eq(rec["otp_hash"], _hash_code(code)):
        attempts = store.increment_otp_attempts(email, purpose)
        if attempts >= MAX_OTP_ATTEMPTS:
            raise OTPLockedOut("尝试次数过多, 请重新获取验证码")
        raise OTPInvalid("验证码错误")

    # 成功 — 一次性消费, 不能复用
    store.delete_otp(email, purpose)


def _purpose_label(purpose: str) -> str:
    return {"register": "注册", "login": "登录"}.get(purpose, purpose)
