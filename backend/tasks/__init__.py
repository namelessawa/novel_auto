"""v2.24 — 后台任务队列。

公共出口
--------
* ``Task`` / ``TaskStatus`` / ``TaskKind`` — Pydantic 契约
* ``TaskManager`` / ``get_task_manager`` — 单例 + 主入口
* ``router`` — FastAPI APIRouter, main.py include 它

设计要点见 task_manager.py 模块文档。
"""

from tasks.task_manager import TaskManager, get_task_manager
from tasks.task_models import Task, TaskKind, TaskStatus
from tasks.task_routes import router

__all__ = [
    "Task",
    "TaskKind",
    "TaskStatus",
    "TaskManager",
    "get_task_manager",
    "router",
]
