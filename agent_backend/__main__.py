"""
``python -m agent_backend`` 启动入口。

通过 subprocess 启动 ``novel_frame/backend/main.py``，规避 ``core`` 包名冲突。

用法:
    python -m agent_backend                  # 默认监听 0.0.0.0:8000 (取自 novel_frame/config.json)
    python -m agent_backend --port 9000      # 覆写端口
    python -m agent_backend --host 127.0.0.1
    python -m agent_backend --reload         # 调试热重载
    python -m agent_backend --uvicorn        # 直接走 uvicorn (默认走 main.py)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from agent_backend import NOVEL_FRAME_BACKEND, PROJECT_ROOT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent_backend", description="FastAPI/SSE 后端")
    parser.add_argument("--host", default=None, help="监听地址 (默认从 config.json 读取)")
    parser.add_argument("--port", type=int, default=None, help="监听端口 (默认从 config.json 读取)")
    parser.add_argument("--reload", action="store_true", help="启用热重载（开发模式）")
    parser.add_argument("--log-level", default="info", help="日志级别 (info / debug / warning)")
    args = parser.parse_args(argv)

    # novel_frame 的 main.py 没有 CLI 参数解析；通过环境变量传递覆盖项
    env = dict(os.environ)
    if args.host:
        env["AGENT_HOST"] = args.host
    if args.port:
        env["AGENT_PORT"] = str(args.port)
    if args.reload:
        env["AGENT_RELOAD"] = "1"
    env["AGENT_LOG_LEVEL"] = args.log_level

    # 主项目根加入 PYTHONPATH 让 settings.py 的 .env 桥接逻辑能找到 dotenv 上下文
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [sys.executable, "main.py"]
    print(f"[agent_backend] launching: {' '.join(cmd)} (cwd={NOVEL_FRAME_BACKEND})", flush=True)
    print(f"[agent_backend] host={args.host or '<settings>'} port={args.port or '<settings>'} "
          f"reload={args.reload}", flush=True)

    try:
        completed = subprocess.run(cmd, cwd=str(NOVEL_FRAME_BACKEND), env=env)
        return completed.returncode
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
