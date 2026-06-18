"""Pydantic v2 模型 — Auth 请求 / 响应 / 用户视图。

EmailStr 走 email-validator 校验; 拒绝畸形邮箱在 422 阶段截掉。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    """对外用户视图 — 不含密码 hash, 不含敏感字段。"""

    id: str
    email: str
    has_password: bool = False
    save_my_works: bool = False
    created_at: datetime
    last_login_at: datetime | None = None


class SendOTPRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class PasswordLoginRequest(BaseModel):
    email: EmailStr
    # 8-128 — 上限挡住客户端故意上传 1MB 字符串吃 bcrypt CPU
    password: str = Field(min_length=8, max_length=128)


class SetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    # current_password 在用户已设过密码时必填, 防 stolen-token + session-fixation 通过
    # 直接改密接管账户。首次设密 (user.has_password=false) 时为空。
    current_password: str = Field(default="", max_length=128)


class UpdateSettingsRequest(BaseModel):
    save_my_works: bool


class AuthResponse(BaseModel):
    token: str
    user: User
