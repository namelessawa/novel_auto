"""
Agent Backend — FastAPI + SSE 后端入口，对应阶段四并行接入。

这是一个**薄壳**包：实际的 agents / pipeline / api 实现复用 ``novel_frame/backend/``
下已有代码，避免源码复制带来的双向同步成本。

设计选择：
- 主项目仍保留 ``main.py`` (CLI) 与 ``frontend/server.js`` (Express + ejs) 路径，
  两条路径继续可用。
- 通过 ``python -m agent_backend`` 启动 FastAPI 后端 (uvicorn)，提供 SSE 流式生成、
  知识图谱与多小说项目管理 API。
- LLM 配置已由阶段一桥接到主项目 ``.env``，因此 ``LLM_PROVIDER`` (deepseek/mimo/custom)
  在两套后端中保持一致。
- 启动方式采用 **subprocess**：直接 ``cd novel_frame/backend && python main.py``。
  这样 novel_frame 的 ``core`` 包不会被主项目同名包遮蔽，运行时干净隔离。
- 数据目录默认仍是 ``novel_frame/backend/data/novels/``。
"""

from __future__ import annotations

import os
from pathlib import Path

# 主项目根 (此文件位于 <root>/agent_backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# novel_frame 后端目录
NOVEL_FRAME_BACKEND = PROJECT_ROOT / "novel_frame" / "backend"

if not NOVEL_FRAME_BACKEND.is_dir():
    raise RuntimeError(
        f"agent_backend 依赖 novel_frame/backend 存在，但未找到: {NOVEL_FRAME_BACKEND}"
    )


__all__ = ["PROJECT_ROOT", "NOVEL_FRAME_BACKEND"]
