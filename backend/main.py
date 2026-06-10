"""Entry point for the Novel Generation Agent System (v2.26 multi-tenant)."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from api.bootstrap_routes import router as bootstrap_router
from api.llm_routes import router as llm_router
from api.image_routes import router as image_router
from api.multimodal_routes import router as multimodal_router
from auth import router as auth_router
from cleanup_task import cleanup_loop
from config.settings import settings
from middleware.user_llm import UserLLMHeadersMiddleware
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

app = FastAPI(
    title="AI 长篇小说生成 Agent 系统",
    description="多 Agent + 7 阶段 Tick 调度 + 邮箱 OTP 认证 + 多租户数据隔离",
    version="2.26.0",
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
# v2.28 — 必须在 CORS 之后注册 (Starlette middleware 栈是 LIFO; 后注册的先执行
# 入站请求); 这样 CORS 先处理 preflight, 再轮到 user-llm middleware 提取 header.
app.add_middleware(UserLLMHeadersMiddleware)

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
app.include_router(bootstrap_router)
app.include_router(tasks_router)


# ---------------------------------------------------------------------------
# 后台任务句柄
# ---------------------------------------------------------------------------

_cleanup_task: asyncio.Task | None = None


@app.on_event("startup")
async def _on_startup() -> None:
    """v2.26 启动钩子.

    1. 一次性迁移 v2.25 旧布局 (data/novels/ → data/users/_legacy/novels/)
    2. 启动 24h cleanup 后台 task
    3. tick runtime 不预热 — 改为 lazy per-user (第一次请求时构造)
    """
    log = logging.getLogger(__name__)

    # 1. legacy 数据迁移 — idempotent, 第二次启动不会再动
    try:
        import novel_manager
        if novel_manager.migrate_legacy_layout():
            log.info(
                "v2.25 → v2.26 legacy data migrated to data/users/_legacy/"
            )
    except Exception as e:
        log.error("legacy migration failed: %s", e)

    # 2. 启动 cleanup 后台 task
    if os.environ.get("DISABLE_CLEANUP", "0") != "1":
        global _cleanup_task
        _cleanup_task = asyncio.create_task(
            cleanup_loop(), name="ephemeral-novel-cleanup"
        )
        log.info("started ephemeral cleanup background task")


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    log = logging.getLogger(__name__)

    # 取消 cleanup
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("cleanup task shutdown error: %s", e)

    # 关闭所有 tick runtime
    try:
        from tick_runtime import close_all_runtimes
        close_all_runtimes()
    except Exception as e:
        log.error("close_all_runtimes failed: %s", e)


# ---------------------------------------------------------------------------
# 健康检查 (公开)
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    return {
        "name": "AI 长篇小说生成 Agent 系统",
        "version": "2.26.0",
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
