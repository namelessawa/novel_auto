"""v2.28 — 把请求 header 里的用户 LLM 凭据塞进 ContextVar.

设计要点
--------
* 用 ASGI middleware 而非 FastAPI Depends — Depends 只对显式声明的路由生效,
  而 LLM 调用发生在 agent 内部 (深嵌于 orchestrator.run_tick), 那里拿不到
  Depends 注入。改用 middleware 在请求入口设 ContextVar, 任何下游代码
  (包括 asyncio.create_task 衍生的后台任务) 都能读到。

* ContextVar 由 ``nf_core.llm_client`` 暴露 ``set_user_llm_config(...) /
  get_user_llm_config()``。Python 标准: asyncio.create_task 默认拷贝当前
  context, 所以用户触发的后台任务自动继承该 tick 的 user_llm 配置。

* 没 header → 不动 ContextVar — 让 ``LLMClient.chat()`` 走 legacy
  config.json 兜底 (兼容 dev / cleanup 等无请求路径)。

* header 名与 ``/api/llm/random-*`` / ``/api/image/generate`` 对齐, 保持一套:
  X-User-LLM-Key, X-User-LLM-Base-Url, X-User-LLM-Model
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from nf_core.llm_client import set_user_llm_config


class UserLLMHeadersMiddleware(BaseHTTPMiddleware):
    """读请求 header → 写 ContextVar — 让下游 llm_client 用用户的 key。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        api_key = request.headers.get("X-User-LLM-Key") or ""
        base_url = request.headers.get("X-User-LLM-Base-Url") or ""
        model = request.headers.get("X-User-LLM-Model") or ""

        # 只要有 api_key 就设 — base_url/model 可缺省 (用 provider 默认)
        if api_key.strip():
            set_user_llm_config(
                api_key=api_key.strip(),
                base_url=base_url.strip(),
                model=model.strip(),
            )
        # 不主动 reset — ContextVar 是 task-scoped, 请求结束自然失效
        return await call_next(request)
