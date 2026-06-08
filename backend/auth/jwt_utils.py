"""JWT (HS256) encode / decode + sliding refresh 判断。

为何 HS256 而不是 RS256: 单后端实例, 不需要分发公钥。运维负担最小。
将来跨服务发证再换。

滑动续期模型: 前端每次拿到响应都看一眼 ``X-Refreshed-Token`` header,
如果存在就替换 localStorage 里的 token。后端在距离过期 < 1 天时签发
一个新 token 塞 header — 这样活跃用户永远不会被踢, 沉睡用户 7 天后
自动失效。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from .config import get_auth_config


class TokenError(Exception):
    """统一 JWT 解码/校验错误 — routes 转 401。"""


def encode_token(user_id: str, email: str) -> str:
    cfg = get_auth_config()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
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
