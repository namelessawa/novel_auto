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

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from nf_core.llm_client import reset_user_llm_config, set_user_llm_config
from nf_core.provider_runtime import ProviderConfigurationError

from .url_safety import is_safe_public_url

_log = logging.getLogger(__name__)


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
        provider = ""
        thinking_mode = ""
        timeout: float | None = None
        max_retries: int | None = None
        header_error = ""
        provider_header_present = False
        for k, v in scope.get("headers", ()):
            value = v.decode("latin-1", "ignore").strip()
            if k == b"x-user-llm-key":
                api_key = value
            elif k == b"x-user-llm-base-url":
                provider_header_present = True
                base_url = value
            elif k == b"x-user-llm-model":
                provider_header_present = True
                model = value
            elif k == b"x-user-llm-provider":
                provider_header_present = True
                provider = value
            elif k == b"x-user-llm-thinking-mode":
                provider_header_present = True
                thinking_mode = value
            elif k == b"x-user-llm-timeout":
                provider_header_present = True
                try:
                    timeout = float(value)
                except ValueError:
                    header_error = "X-User-LLM-Timeout 必须是正数"
            elif k == b"x-user-llm-max-retries":
                provider_header_present = True
                try:
                    max_retries = int(value)
                except ValueError:
                    header_error = "X-User-LLM-Max-Retries 必须是非负整数"

        if header_error:
            await JSONResponse(
                status_code=400,
                content={
                    "detail": {
                        "code": "PROVIDER_CONFIG_INVALID",
                        "message": header_error,
                        "details": {},
                    }
                },
            )(scope, receive, send)
            return

        # Never replace an unsafe user endpoint with a different provider's
        # endpoint: doing so could send the user's credential to the wrong
        # service.  The response intentionally does not echo the rejected URL.
        if base_url and not is_safe_public_url(base_url):
            _log.warning("rejected unsafe user-supplied LLM base URL")
            await JSONResponse(
                status_code=400,
                content={
                    "detail": {
                        "code": "PROVIDER_BASE_URL_UNSAFE",
                        "message": "X-User-LLM-Base-Url 必须是公网 https:// 地址",
                        "details": {},
                    }
                },
            )(scope, receive, send)
            return

        if not api_key and provider_header_present:
            await JSONResponse(
                status_code=400,
                content={
                    "detail": {
                        "code": "PROVIDER_CREDENTIAL_REQUIRED",
                        "message": "提供模型配置 header 时必须同时提供 API key",
                        "details": {},
                    }
                },
            )(scope, receive, send)
            return

        token = None
        if api_key:
            try:
                token = set_user_llm_config(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                    provider=provider,
                    thinking_mode=thinking_mode,
                    timeout=timeout,
                    max_retries=max_retries,
                )
            except ProviderConfigurationError as exc:
                await JSONResponse(
                    status_code=422,
                    content={
                        "detail": {
                            "code": "PROVIDER_CONFIG_INVALID",
                            "message": str(exc),
                            "details": {},
                        }
                    },
                )(scope, receive, send)
                return

        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                reset_user_llm_config(token)
