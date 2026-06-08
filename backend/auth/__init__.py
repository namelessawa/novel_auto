"""v2.26 — Auth package.

邮箱 OTP 注册 + 可选密码登录 + JWT 7d 滑动会话 + 每用户数据命名空间。

设计要点
--------
* SMTP-based 6 位 OTP 注册; 注册成功后可在设置里加密码 (passlib bcrypt)。
* 登录支持 OTP 或密码; 二者走独立路径独立限流。
* JWT HS256, 7d 过期, 每次受保护请求经 ``get_current_user`` 取出当前用户。
  滑动续期在前端层做: 响应 header 若带新 token, 替换 localStorage。
* 内存限流: 每 IP / 每邮箱独立计数, 进程重启清零 (适合单进程后端;
  多进程要换 Redis)。
* 用户数据按 ``data/users/{user_id}/novels/{novel_id}/`` 命名空间隔离。
  ``save_my_works=False`` (默认) 时 24h 未访问被清理任务删除。
* ``LEGACY_USER_ID = "_legacy"`` — 升级前已存在的 novel 全部迁移到此命名
  空间, save_my_works=True 保证不被清理。

模块依赖图
----------
``models`` ← ``store`` ← ``otp`` ← ``routes``
``config`` ← ``jwt_utils`` / ``smtp_client`` / ``rate_limit`` ← ``routes``
``store`` + ``jwt_utils`` ← ``dependencies`` ← ``routes``
"""
from __future__ import annotations

from .dependencies import (
    LEGACY_USER_ID,
    get_client_ip,
    get_current_user,
    get_optional_user,
    to_user,
)
from .models import User
from .routes import router

__all__ = [
    "LEGACY_USER_ID",
    "User",
    "get_client_ip",
    "get_current_user",
    "get_optional_user",
    "router",
    "to_user",
]
