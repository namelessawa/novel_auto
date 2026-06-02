"""Entry point for the Novel Generation Agent System."""

import logging
import os
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.routes import router
from api.tick_routes import router as tick_router
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="AI 长篇小说生成 Agent 系统",
    description="多模块协同的 Agent 架构，实现百万字级逻辑连贯的长篇小说生成",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
# tick 架构控制路由(prefix=/api/tick); 路由会在 Orchestrator 实例化前返回 503
app.include_router(tick_router)


@app.on_event("startup")
async def _build_tick_runtime() -> None:
    """启动时装配 Orchestrator + TickState + TickDB,注入到 tick_routes 全局容器。

    通过 ``DISABLE_TICK_RUNTIME=1`` 可禁用(用于纯 legacy 模式)。
    """
    if os.environ.get("DISABLE_TICK_RUNTIME", "0") == "1":
        logging.getLogger(__name__).info("tick runtime disabled by env")
        return
    try:
        from tick_runtime import get_runtime
        get_runtime()
        logging.getLogger(__name__).info("tick runtime ready - /api/tick routes active")
    except Exception as e:
        logging.getLogger(__name__).error("tick runtime init failed: %s", e)


@app.on_event("shutdown")
async def _close_tick_runtime() -> None:
    try:
        from tick_runtime import close_runtime
        close_runtime()
    except Exception:
        pass


@app.get("/")
async def root():
    return {
        "name": "AI 长篇小说生成 Agent 系统",
        "version": "1.0.0",
        "status": "running",
    }


if __name__ == "__main__":
    # 允许通过环境变量覆盖（agent_backend 启动器使用）
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
