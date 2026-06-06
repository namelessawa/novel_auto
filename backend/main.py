"""Entry point for the Novel Generation Agent System (tick architecture)."""

from __future__ import annotations

import logging
import os
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))

# 让 backend/ 顶级模块 (api / config / agents / ...) 与项目根 (memory_system /
# core / evaluation) 同时可 import
for p in (_PROJECT_ROOT, _BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.routes import router
from api.tick_routes import router as tick_router
from api.agent_routes import router as agent_router
from api.section_routes import router as section_router
from api.bootstrap_routes import router as bootstrap_router
from tasks import router as tasks_router
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# v2.24 — uvicorn access log 屏蔽 2xx/3xx 行, 让监控界面只显示真正需要关注的
# 4xx / 5xx。默认 uvicorn 把所有请求都 INFO 打出来, 前端 3s 一次 /api/tick/status
# 把日志冲得几乎只剩 "200 OK" 噪声 — 重要错误被淹没。
#
# uvicorn AccessFormatter 把 record.args 设为 (client_addr, request_line, status_code)。
# 兜底任意 args 形态: 找不到 status_code 就保留这行 (宁可多打不漏)。
class _AccessLogFilter(logging.Filter):
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
        # 200-399 视为正常 — 不显示
        return not (200 <= status < 400)


logging.getLogger("uvicorn.access").addFilter(_AccessLogFilter())

app = FastAPI(
    title="AI 长篇小说生成 Agent 系统",
    description="多 Agent + 7 阶段 Tick 调度的多智能体小说生成系统",
    version="2.0.0",
)

# Vite dev server 默认 3143;生产从 frontend/dist 直接 serve 时这里其实不会触发跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(tick_router)
app.include_router(agent_router)
app.include_router(section_router)
app.include_router(bootstrap_router)
app.include_router(tasks_router)


@app.on_event("startup")
async def _build_tick_runtime() -> None:
    """启动时装配 Orchestrator + TickState + TickDB,注入到 tick_routes 全局容器。

    通过 ``DISABLE_TICK_RUNTIME=1`` 可禁用(用于纯 API 调试)。

    v2.17 — 关键一致性: 解析「权威启动默认 novel_id」(novel_manager 视角),
    用同一 id 装配 tick runtime 并同步给 legacy ``_active_novel_id``。否则
    manifest 第一项 ≠ ACTIVE_NOVEL_ID 时,/api/stats 与 /api/tick/* 会分别指向
    不同小说,UI 首屏数据错位。
    """
    log = logging.getLogger(__name__)

    # 先解析权威默认 — 即使禁用 tick runtime, legacy pipeline 也需要这个对齐
    try:
        import novel_manager
        from api.routes import set_active_novel_id

        default_id = novel_manager.resolve_default_novel_id()
        set_active_novel_id(default_id)
    except Exception as e:
        log.error("default novel resolution failed: %s", e)
        default_id = None

    if os.environ.get("DISABLE_TICK_RUNTIME", "0") == "1":
        log.info("tick runtime disabled by env")
        return
    try:
        from tick_runtime import set_active_novel, get_runtime

        if default_id:
            # 用 set_active_novel 而非裸 get_runtime() — 这样 tick runtime 与
            # legacy 用同一 novel_id,且 /api/tick/* 路由容器立刻指向它。
            set_active_novel(default_id)
        else:
            get_runtime()
        log.info(
            "tick runtime ready - /api/tick routes active (novel='%s')",
            default_id or "<env-default>",
        )
    except Exception as e:
        log.error("tick runtime init failed: %s", e)


@app.on_event("shutdown")
async def _close_tick_runtime() -> None:
    try:
        from tick_runtime import close_runtime

        close_runtime()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 健康检查 API
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health() -> dict:
    return {
        "name": "AI 长篇小说生成 Agent 系统",
        "version": "2.0.0",
        "status": "running",
    }


# ---------------------------------------------------------------------------
# 前端静态资源
# ---------------------------------------------------------------------------
# 优先级:
#   1. 若 frontend/dist 存在(npm run build 产物) → 由 FastAPI 直接 serve;
#      根路径 / 重定向到 /nw/(Vite base);未匹配的前端路由回落到 index.html。
#   2. 否则给一个简短提示 JSON,提醒先 build 或开 Vite dev server。

_FRONTEND_DIST = os.path.join(_PROJECT_ROOT, "frontend", "dist")
_VITE_BASE = "/nw"

if os.path.isdir(_FRONTEND_DIST):
    # /nw/ 下挂载 SPA 静态资源(与 vite.config.js 的 base 对齐)
    app.mount(
        f"{_VITE_BASE}/",
        StaticFiles(directory=_FRONTEND_DIST, html=True),
        name="frontend",
    )

    @app.get("/")
    async def _root_redirect() -> FileResponse:
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))

else:

    @app.get("/")
    async def _root_hint() -> dict:
        return {
            "name": "AI 长篇小说生成 Agent 系统",
            "version": "2.0.0",
            "status": "running",
            "frontend": "未发现 frontend/dist。开发请运行 `cd frontend && npm run dev`,生产请 `npm run build`。",
            "endpoints": {
                "health": "/api/health",
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
