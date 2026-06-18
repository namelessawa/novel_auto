"""Sliding JWT refresh — 纯 ASGI middleware.

每个带 Authorization: Bearer <jwt> 的请求, 如果 token 距离过期 < 1 天, 就在响应里
加一个 ``X-Refreshed-Token`` header (前端 authedFetch 看到此 header 就替换 localStorage)。

为何用 ASGI 而不是 BaseHTTPMiddleware: 后者在错误响应路径会丢 header / 触发
ContextVar 边缘案例。纯 ASGI 通过 wrap send 函数, 直接改 response.start 的 headers,
500 / 422 / 401 路径同样能加上。

CORS: 想让浏览器 JS 读到自定义响应头, 必须 ``Access-Control-Expose-Headers: X-Refreshed-Token``。
``main.py`` 的 CORSMiddleware 配置时显式列入。
"""
from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from auth.jwt_utils import (
    TokenError,
    decode_token,
    encode_token,
    is_near_expiry,
    is_revoked,
)
from auth.store import get_user_store

_log = logging.getLogger(__name__)


class SlidingRefreshMiddleware:
    """near-expiry → 签新 token 塞响应 header。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        new_token: str | None = None
        token = ""
        for k, v in scope.get("headers", ()):
            if k == b"authorization":
                val = v.decode("latin-1", "ignore").strip()
                if val.lower().startswith("bearer "):
                    token = val[7:].strip()
                break

        if token:
            try:
                payload = decode_token(token)
                if is_near_expiry(payload, threshold_days=1) and not is_revoked(
                    payload.get("jti")
                ):
                    user_id = payload.get("sub")
                    if user_id:
                        # SQLite get_by_id 是同步, 在中间件里短查询可接受 (~1ms);
                        # 想严格避免 event loop 阻塞可包 run_in_threadpool, 但成本
                        # 反而高于查询本身。
                        row = get_user_store().get_by_id(user_id)
                        if row is not None:
                            # 仅当 pv 一致时才续签 — 否则原 token 本来就该 401, 续签反而救活了它
                            if int(payload.get("pv") or 0) == int(
                                row.get("password_version") or 0
                            ):
                                new_token = encode_token(
                                    row["id"],
                                    row["email"],
                                    password_version=int(
                                        row.get("password_version") or 0
                                    ),
                                )
            except TokenError:
                pass
            except Exception:
                # 中间件绝不能阻塞响应 — 任何失败都静默, 让请求按原路走
                _log.exception("sliding refresh failed (non-fatal)")

        if new_token is None:
            await self.app(scope, receive, send)
            return

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-refreshed-token", new_token.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, _send)
