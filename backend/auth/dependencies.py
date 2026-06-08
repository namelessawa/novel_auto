"""FastAPI Depends — get_current_user / get_optional_user / get_client_ip。

LEGACY_USER_ID — 升级前已存在的 novel 全部迁移到此命名空间, 是"系统创世前
的数据归属"。新注册用户拿不到这些数据 (multi-tenant 隔离), 但管理员可手动
迁移。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_auth_config
from .jwt_utils import TokenError, decode_token
from .models import User
from .store import get_user_store

LEGACY_USER_ID = "_legacy"

# auto_error=False — 让我们自己抛 401 (而不是 403), 同时给 optional 路径用
_bearer = HTTPBearer(auto_error=False)


def get_client_ip(request: Request) -> str:
    """提取真实客户端 IP, 兼容 Cloudflare Tunnel / 反代 / 直连。

    优先级: CF-Connecting-IP > X-Forwarded-For 首个 > request.client.host
    """
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def to_user(row: dict) -> User:
    return User(
        id=row["id"],
        email=row["email"],
        has_password=bool(row.get("password_hash")),
        save_my_works=bool(row.get("save_my_works")),
        created_at=datetime.fromtimestamp(row["created_at"], tz=timezone.utc),
        last_login_at=(
            datetime.fromtimestamp(row["last_login_at"], tz=timezone.utc)
            if row.get("last_login_at")
            else None
        ),
    )


def _legacy_user() -> User:
    """当 auth.enabled=false 时使用的合成用户 — 走兼容路径不强制登录。

    save_my_works=True 保证 legacy 数据不被 24h 清理任务删除。
    """
    return User(
        id=LEGACY_USER_ID,
        email="legacy@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """解码 JWT → 查 DB → 返回 User。任一步失败抛 401。

    auth.enabled=false 时直接返回合成 legacy user (开发 / 迁移期)。
    """
    cfg = get_auth_config()
    if not cfg.enabled:
        return _legacy_user()

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials)
    except TokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录态无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="登录态无效")
    row = get_user_store().get_by_id(user_id)
    if row is None:
        # 用户被删除 / DB 切换 — 当作未登录
        raise HTTPException(status_code=401, detail="用户不存在")
    return to_user(row)


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User | None:
    """像 get_current_user 但 401 时返回 None — 给两栖端点用 (例如 /api/llm/random-*
    在登录前的探索性调用)。"""
    if credentials is None or not credentials.credentials:
        return None
    try:
        return get_current_user(credentials)
    except HTTPException:
        return None
