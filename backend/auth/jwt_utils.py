"""JWT (HS256) encode / decode + sliding refresh 判断 + 服务端 jti 撤销 + 密码版本绑定。

为何 HS256 而不是 RS256: 单后端实例, 不需要分发公钥。运维负担最小。
将来跨服务发证再换。

会话失效路径:
  1. 自然过期: ``exp`` 到期 (默认 7 天)
  2. 服务端撤销: ``logout`` 把当前 ``jti`` 写入内存撤销表 (TTL 与 exp 对齐)
  3. 密码变更: ``set-password`` 自增 ``store.users.password_version``,
     旧 token 的 ``pv`` 不匹配即 401

滑动续期: 由 ``middleware.sliding_refresh`` 实现 — 在响应阶段读 Authorization,
距离过期 < 1 天时签新 token 塞到 ``X-Refreshed-Token`` 响应头, 前端拿到后替换
localStorage。
"""
from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from .config import get_auth_config


class TokenError(Exception):
    """统一 JWT 解码/校验错误 — routes 转 401。"""


# 内存撤销表 — jti -> exp_timestamp。lazy cleanup 在每次 revoke 时跑一次。
# 单实例部署够用; 多实例需要外部存储 (Redis) 同步。
_revoked_jti: dict[str, float] = {}
_revoked_lock = threading.Lock()


def encode_token(user_id: str, email: str, password_version: int = 0) -> str:
    cfg = get_auth_config()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        # pv 与 store.users.password_version 绑定: 改密码后 db 自增 → token 校验失败
        "pv": int(password_version),
        # jti 让 logout 能精确撤销当前会话, 而不是全用户登出
        "jti": secrets.token_urlsafe(16),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=cfg.jwt_ttl_days)).timestamp()),
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def decode_token(token: str) -> dict:
    cfg = get_auth_config()
    try:
        return jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    except JWTError as e:
        raise TokenError(str(e)) from e


def is_near_expiry(payload: dict, threshold_days: int = 1) -> bool:
    """若 token 距离过期 < threshold_days, 触发滑动续期。"""
    exp_ts = payload.get("exp")
    if not isinstance(exp_ts, (int, float)):
        return False
    exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
    return exp_dt - datetime.now(timezone.utc) < timedelta(days=threshold_days)


def revoke_token(payload: dict) -> None:
    """把 token 的 jti 加入撤销表, 直到原本的 exp 才清除。"""
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not isinstance(exp, (int, float)):
        return
    now = datetime.now(timezone.utc).timestamp()
    with _revoked_lock:
        # lazy cleanup: 一次扫一遍, 撤销表只在 logout 路径增长, 不会爆炸
        expired = [k for k, v in _revoked_jti.items() if v < now]
        for k in expired:
            _revoked_jti.pop(k, None)
        _revoked_jti[jti] = float(exp)


def is_revoked(jti: str | None) -> bool:
    if not jti:
        return False
    with _revoked_lock:
        return jti in _revoked_jti


def _clear_revoked_for_tests() -> None:
    with _revoked_lock:
        _revoked_jti.clear()
