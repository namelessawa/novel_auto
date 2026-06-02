"""Run the FastAPI tick backend.

用法:
    python run.py                    # 默认 host=settings.host, port=settings.port
    python run.py --reload           # dev 模式
    AGENT_PORT=8001 python run.py    # 通过环境变量覆盖
"""

from __future__ import annotations

import argparse
import os
import sys

# 让 backend/ 顶级模块可 import
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(_PROJECT_ROOT, "backend")
for p in (_PROJECT_ROOT, _BACKEND_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


def main() -> int:
    parser = argparse.ArgumentParser(description="Novel-auto tick backend launcher")
    parser.add_argument("--host", default=os.environ.get("AGENT_HOST"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("AGENT_PORT", "0")) or None)
    parser.add_argument("--reload", action="store_true", default=os.environ.get("AGENT_RELOAD", "0") == "1")
    parser.add_argument("--log-level", default=os.environ.get("AGENT_LOG_LEVEL", "info"))
    args = parser.parse_args()

    import uvicorn
    from config.settings import settings

    host = args.host or settings.host
    port = args.port or settings.port

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level=args.log_level,
        app_dir=_BACKEND_DIR,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
