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
