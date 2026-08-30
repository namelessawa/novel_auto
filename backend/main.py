"""Entry point for the Novel Generation Agent System (v2.26 multi-tenant)."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))

for p in (_PROJECT_ROOT, _BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.routes import router
from api.tick_routes import router as tick_router
from api.agent_routes import router as agent_router
from api.section_routes import router as section_router
from api.story_routes import router as story_router
from api.bootstrap_routes import router as bootstrap_router
from api.llm_routes import router as llm_router
from api.image_routes import router as image_router
from api.multimodal_routes import router as multimodal_router
from api.production_control_routes import router as production_control_router
from api.production_routes import router as production_router
from api.pipeline_routes import router as pipeline_router
from auth import router as auth_router
from cleanup_task import cleanup_loop
from config.settings import settings
from middleware.sliding_refresh import SlidingRefreshMiddleware
from middleware.user_llm import UserLLMHeadersMiddleware
from nf_core.provider_runtime import ProviderConfigurationError, ProviderError
from tasks import router as tasks_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class _AccessLogFilter(logging.Filter):
    """uvicorn access log 屏蔽 2xx/3xx 行, 让监控只剩真正的 4xx/5xx。"""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        status: int | None = None
        if isinstance(args, tuple):
            for item in args:
                if isinstance(item, int) and 100 <= item < 600:
                    status = item
                    break
        elif isinstance(args, dict):
            raw = args.get("status_code")
            if isinstance(raw, int):
                status = raw
        if status is None:
            return True
        return not (200 <= status < 400)


logging.getLogger("uvicorn.access").addFilter(_AccessLogFilter())

_cleanup_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan — 替代弃用的 ``@app.on_event('startup'/'shutdown')``。

    启动顺序:
      1. legacy 数据迁移 (idempotent)
      2. 启动 24h cleanup 后台任务

    关闭顺序: 反向 — 先取消 cleanup, 再关闭所有 tick runtime。
    """
    log = logging.getLogger(__name__)

    # legacy 数据迁移
    try:
        import novel_manager
        if novel_manager.migrate_legacy_layout():
            log.info("v2.25 → v2.26 legacy data migrated to data/users/_legacy/")
    except Exception as e:
        log.error("legacy migration failed: %s", e)

    # Durable whole-book jobs are reconstructed from journals.  Pytest never
    # starts background production implicitly; its suites inject recorded
    # runners explicitly.
    if (
        os.environ.get("DISABLE_PRODUCTION_RECOVERY", "0") != "1"
        and "PYTEST_CURRENT_TEST" not in os.environ
    ):
        try:
            from story.production_runtime import recover_persisted_productions

            recovered = await recover_persisted_productions()
            if recovered:
                log.info("scheduled %s durable production job(s)", recovered)
        except Exception as e:
            log.error("production startup recovery failed: %s", type(e).__name__)

    # cleanup 后台任务
    global _cleanup_task
    if os.environ.get("DISABLE_CLEANUP", "0") != "1":
        _cleanup_task = asyncio.create_task(
            cleanup_loop(), name="ephemeral-novel-cleanup"
        )
        log.info("started ephemeral cleanup background task")

    yield

    # 关停: 反向, 先 cleanup, 再 runtime
    if _cleanup_task is not None and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("cleanup task shutdown error: %s", e)

    try:
        from story.production_runtime import close_all_production_runtimes

        await close_all_production_runtimes()
    except Exception as e:
        log.error("close_all_production_runtimes failed: %s", type(e).__name__)

    try:
        from tick_runtime import close_all_runtimes
        close_all_runtimes()
    except Exception as e:
        log.error("close_all_runtimes failed: %s", e)

    try:
        from nf_core.llm_client import llm_client

        await llm_client.aclose()
    except Exception as e:
        log.error("provider client shutdown failed: %s", e)


app = FastAPI(
    title="AI 长篇小说作者生产系统",
    description=(
        "默认使用整书规格、大纲和可恢复 Author 事务链；"
        "九 Agent Tick 世界模拟仅保留在实验入口。"
    ),
    version="2.49+unreleased",
    lifespan=lifespan,
)


@app.exception_handler(ProviderConfigurationError)
async def _provider_configuration_error_handler(
    request: Request,
    exc: ProviderConfigurationError,
) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "PROVIDER_CONFIG_INVALID",
                "message": str(exc),
                "details": {},
            }
        },
    )


@app.exception_handler(ProviderError)
async def _provider_error_handler(
    request: Request,
    exc: ProviderError,
) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=exc.http_status,
        content={"detail": exc.to_detail()},
    )

def _cors_policy(origins: list[str]) -> tuple[list[str], bool]:
    """v2.37 — origins 含 "*" 时禁用 credentials。

    CORS 规范禁止 ``Access-Control-Allow-Origin: *`` 与
    ``Access-Control-Allow-Credentials: true`` 并用 — 浏览器会直接拒绝带
    Authorization 的跨域请求, 等于全站登录失效。生产请在 config.json
    server.cors_origins 显式列出前端域名。
    """
    if "*" in origins:
        logging.getLogger(__name__).warning(
            "cors_origins 含 '*' — 已自动关闭 allow_credentials (CORS 规范禁止"
            "两者并用)。跨域携带 Authorization 的请求将失败; 请在 config.json "
            "server.cors_origins 显式列出前端域名。"
        )
        return origins, False
    return origins, True


_cors_origins, _cors_allow_credentials = _cors_policy(settings.cors_origins)

# Starlette wraps middleware in reverse registration order.  Register request
# context and refresh first, then CORS last so CORS is outermost: preflight is
# handled before credential parsing and middleware-generated provider 4xx
# responses still receive browser-readable CORS headers.
app.add_middleware(UserLLMHeadersMiddleware)
app.add_middleware(SlidingRefreshMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    # X-Refreshed-Token 让前端 authedFetch 能读到 sliding refresh 签的新 token,
    # 不显式 expose 浏览器跨域请求里 JS 拿不到。
    expose_headers=["X-Refreshed-Token"],
)

# v2.26 — auth_router 必须在所有受保护 router 之前注册 (FastAPI 路由匹配顺序无关
# 但日志可读性: 让 /api/auth/* 优先出现)
app.include_router(auth_router)
app.include_router(llm_router)
app.include_router(image_router)
app.include_router(multimodal_router)
app.include_router(router)
app.include_router(tick_router)
app.include_router(agent_router)
app.include_router(section_router)
app.include_router(story_router)
app.include_router(production_router)
app.include_router(production_control_router)
app.include_router(pipeline_router)
app.include_router(bootstrap_router)
app.include_router(tasks_router)


# ---------------------------------------------------------------------------
# 健康检查 (公开)
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    return {
        "name": "AI 长篇小说作者生产系统",
        "version": "2.49+unreleased",
        "status": "running",
        "auth": "email-otp + optional password",
    }


# ---------------------------------------------------------------------------
# 前端静态资源
# ---------------------------------------------------------------------------

_FRONTEND_DIST = os.path.join(_PROJECT_ROOT, "frontend", "dist")

if os.path.isdir(_FRONTEND_DIST):
    app.mount(
        "/",
        StaticFiles(directory=_FRONTEND_DIST, html=True),
        name="frontend",
    )

else:

    @app.get("/")
    async def _root_hint() -> dict:
        return {
            "name": "AI 长篇小说生成 Agent 系统",
            "version": "2.26.0",
            "status": "running",
            "frontend": (
                "未发现 frontend/dist。开发请运行 `cd frontend && npm run dev`,"
                "生产请 `npm run build`。"
            ),
            "endpoints": {
                "health": "/api/health",
                "auth": "/api/auth/*",
                "tick_status": "/api/tick/status",
                "config": "/api/config",
            },
        }


if __name__ == "__main__":
    host = os.environ.get("AGENT_HOST", settings.host)
    port = int(os.environ.get("AGENT_PORT", settings.port))
    reload_enabled = os.environ.get("AGENT_RELOAD", "0") == "1"
    log_level = os.environ.get("AGENT_LOG_LEVEL", "info")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level=log_level,
    )
