"""/api/auth/* — 9 个端点。

| Method | Path                          | 用途                       | Auth |
|--------|-------------------------------|----------------------------|------|
| POST   | /api/auth/register/send-otp   | 注册第 1 步: 发 OTP        | -    |
| POST   | /api/auth/register/verify     | 注册第 2 步: 校验 + 创建    | -    |
| POST   | /api/auth/login/send-otp      | 登录-OTP 模式第 1 步       | -    |
| POST   | /api/auth/login/verify-otp    | 登录-OTP 模式第 2 步       | -    |
| POST   | /api/auth/login/password      | 登录-密码模式              | -    |
| POST   | /api/auth/me/set-password     | 设置/更新密码 (设置面板)   | ✓    |
| GET    | /api/auth/me                  | 当前用户视图               | ✓    |
| PUT    | /api/auth/me/settings         | 更新 save_my_works 开关    | ✓    |
| POST   | /api/auth/logout              | 客户端清 token (服务端 noop)| ✓    |

存在性泄露防御
--------------
login/send-otp 对未注册邮箱返回 204 不发邮件 (不暴露邮箱是否存在);
login/verify-otp 对未注册邮箱返回"验证码错误";
login/password 错误邮箱与错误密码返回同一文案与状态码。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .config import get_auth_config
from .dependencies import get_client_ip, get_current_user, to_user
from .jwt_utils import encode_token
from .models import (
    AuthResponse,
    PasswordLoginRequest,
    SendOTPRequest,
    SetPasswordRequest,
    UpdateSettingsRequest,
    User,
    VerifyOTPRequest,
)
from .otp import (
    OTPExpired,
    OTPInvalid,
    OTPLockedOut,
    send_otp,
    verify_otp,
)
from .password import hash_password, verify_password
from .rate_limit import RateLimit, get_rate_limiter
from .smtp_client import SMTPError
from .store import get_user_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---- 限流策略 — 每次取以反映 config.json hot-reload --------------------
def _rate(scope: str, key: str, limit: RateLimit) -> None:
    if not get_rate_limiter().check_and_record(scope, key, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁, 请稍后再试",
        )


def _policy_send_otp_ip() -> RateLimit:
    c = get_auth_config()
    return RateLimit(c.otp_send_per_ip_per_hour, 3600)


def _policy_send_otp_email() -> RateLimit:
    c = get_auth_config()
    return RateLimit(c.otp_send_per_email_per_hour, 3600)


def _policy_verify_ip() -> RateLimit:
    c = get_auth_config()
    return RateLimit(c.otp_verify_per_ip_per_15min, 900)


def _policy_pwlogin_ip() -> RateLimit:
    c = get_auth_config()
    return RateLimit(c.password_login_per_ip_per_15min, 900)


def _policy_pwlogin_email() -> RateLimit:
    c = get_auth_config()
    return RateLimit(c.password_login_per_email_per_15min, 900)


# ---- 注册 ---------------------------------------------------------------
@router.post("/register/send-otp", status_code=204)
async def register_send_otp(req: SendOTPRequest, request: Request) -> None:
    ip = get_client_ip(request)
    email = req.email.lower()
    _rate("otp_send_ip", ip, _policy_send_otp_ip())
    _rate("otp_send_email", email, _policy_send_otp_email())

    if get_user_store().get_by_email(email) is not None:
        raise HTTPException(409, detail="该邮箱已注册, 请直接登录")
    try:
        await send_otp(email, "register")
    except SMTPError as e:
        raise HTTPException(503, detail=f"邮件发送失败: {e}")


@router.post("/register/verify", response_model=AuthResponse)
async def register_verify(req: VerifyOTPRequest, request: Request) -> AuthResponse:
    ip = get_client_ip(request)
    _rate("otp_verify_ip", ip, _policy_verify_ip())

    email = req.email.lower()
    store = get_user_store()
    if store.get_by_email(email) is not None:
        raise HTTPException(409, detail="该邮箱已注册")
    try:
        verify_otp(email, "register", req.otp)
    except OTPInvalid as e:
        raise HTTPException(400, detail=str(e))
    except OTPExpired as e:
        raise HTTPException(400, detail=str(e))
    except OTPLockedOut as e:
        raise HTTPException(429, detail=str(e))

    row = store.create(email)
    store.touch_last_login(row["id"])
    user = to_user(store.get_by_id(row["id"]))
    token = encode_token(user.id, user.email)
    return AuthResponse(token=token, user=user)


# ---- 登录 ---------------------------------------------------------------
@router.post("/login/send-otp", status_code=204)
async def login_send_otp(req: SendOTPRequest, request: Request) -> None:
    ip = get_client_ip(request)
    email = req.email.lower()
    _rate("otp_send_ip", ip, _policy_send_otp_ip())
    _rate("otp_send_email", email, _policy_send_otp_email())

    if get_user_store().get_by_email(email) is None:
        # 不泄露邮箱存在性: 静默返回 204, 真实邮箱才发送邮件
        return None
    try:
        await send_otp(email, "login")
    except SMTPError as e:
        raise HTTPException(503, detail=f"邮件发送失败: {e}")


@router.post("/login/verify-otp", response_model=AuthResponse)
async def login_verify_otp(req: VerifyOTPRequest, request: Request) -> AuthResponse:
    ip = get_client_ip(request)
    _rate("otp_verify_ip", ip, _policy_verify_ip())

    email = req.email.lower()
    store = get_user_store()
    row = store.get_by_email(email)
    if row is None:
        # 未注册邮箱直接返回"验证码错误"而非"用户不存在"
        raise HTTPException(400, detail="验证码错误或已过期")
    try:
        verify_otp(email, "login", req.otp)
    except OTPInvalid as e:
        raise HTTPException(400, detail=str(e))
    except OTPExpired as e:
        raise HTTPException(400, detail=str(e))
    except OTPLockedOut as e:
        raise HTTPException(429, detail=str(e))

    store.touch_last_login(row["id"])
    user = to_user(store.get_by_id(row["id"]))
    token = encode_token(user.id, user.email)
    return AuthResponse(token=token, user=user)


@router.post("/login/password", response_model=AuthResponse)
async def login_password(
    req: PasswordLoginRequest, request: Request
) -> AuthResponse:
    ip = get_client_ip(request)
    email = req.email.lower()
    _rate("pw_login_ip", ip, _policy_pwlogin_ip())
    _rate("pw_login_email", email, _policy_pwlogin_email())

    store = get_user_store()
    row = store.get_by_email(email)
    # 统一错误文案 — 不暴露邮箱是否存在 / 是否设过密码
    error = HTTPException(401, detail="邮箱或密码错误")
    if row is None or not row.get("password_hash"):
        # 仍然执行一次 hash 避免 timing 侧信道 (cost 12 是固定时长)
        verify_password(req.password, "$2b$12$" + "x" * 53)
        raise error
    if not verify_password(req.password, row["password_hash"]):
        raise error

    store.touch_last_login(row["id"])
    user = to_user(store.get_by_id(row["id"]))
    token = encode_token(user.id, user.email)
    return AuthResponse(token=token, user=user)


# ---- 受保护端点 ---------------------------------------------------------
@router.post("/me/set-password", status_code=204)
async def set_password(
    req: SetPasswordRequest,
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        get_user_store().update_password(current_user.id, hash_password(req.password))
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


@router.get("/me", response_model=User)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.put("/me/settings", response_model=User)
async def update_settings(
    req: UpdateSettingsRequest,
    current_user: User = Depends(get_current_user),
) -> User:
    store = get_user_store()
    store.update_save_my_works(current_user.id, req.save_my_works)
    return to_user(store.get_by_id(current_user.id))


@router.post("/logout", status_code=204)
async def logout(current_user: User = Depends(get_current_user)) -> None:
    """无状态 JWT — 服务端无 session, 客户端清 token 即登出。

    保留端点是为给前端一个 idempotent 端点 + 给将来的 token 黑名单留口子。
    """
    return None
