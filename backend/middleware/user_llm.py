"""v2.28 — 把请求 header 里的用户 LLM 凭据塞进 ContextVar.

设计要点
--------
* 用纯 ASGI middleware (不是 BaseHTTPMiddleware) — 后者在错误响应路径有已知的
  contextvar / CORS 头丢失边缘案例 (响应是 5xx 时, CORSMiddleware 的 ALLOW-ORIGIN
  头偶尔没正确加上, 浏览器读不到 body). 纯 ASGI 没这个问题, 也更轻量.

* ContextVar 由 ``nf_core.llm_client`` 暴露 ``set_user_llm_config / get_user_llm_config``.
  asyncio.create_task 默认拷贝当前 context, 所以 /api/section/generate 衍生的后台
  任务也能继承该请求的凭据.

* 没 header → 不动 ContextVar — 让 LLMClient.chat() 走 config.json 兜底 (兼容 dev /
  cleanup 等无请求路径).

* header 名与 /api/llm/random-* 对齐:
  X-User-LLM-Key, X-User-LLM-Base-Url, X-User-LLM-Model
"""
from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from nf_core.llm_client import set_user_llm_config


class UserLLMHeadersMiddleware:
    """纯 ASGI middleware: 入站 header → ContextVar."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # ASGI scope["headers"] 是 list[tuple[bytes, bytes]], 小写键
        api_key = ""
        base_url = ""
        model = ""
        for k, v in scope.get("headers", ()):
            if k == b"x-user-llm-key":
                api_key = v.decode("latin-1", "ignore").strip()
            elif k == b"x-user-llm-base-url":
                base_url = v.decode("latin-1", "ignore").strip()
            elif k == b"x-user-llm-model":
                model = v.decode("latin-1", "ignore").strip()

        if api_key:
            set_user_llm_config(api_key=api_key, base_url=base_url, model=model)

        await self.app(scope, receive, send)
