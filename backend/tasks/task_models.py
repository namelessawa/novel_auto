"""v2.24 任务契约 — 前后端共享的 Pydantic 模型。

Task 是不可变快照: 每次 progress 更新生成新副本, SSE 推送的就是这个对象。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskKind = Literal["section_generation", "bootstrap_section"]
TaskStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class TaskProgress(BaseModel):
    """续写任务进度子结构 — 字数 + tick 计数双指标。"""

    model_config = ConfigDict(extra="ignore")

    current_words: int = 0
    target_words: int = 3000
    min_words: int = 2400
    tick_count: int = 0
    max_ticks: int = 30
    current_tick: int | None = None
    last_message: str = ""


class Task(BaseModel):
    """前后端共享的任务快照。

    所有时间字段用 ISO-8601 字符串而非 datetime, 避免前端 JSON 反序列化时区出错。
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    novel_id: str
    novel_title: str = ""
    kind: TaskKind
    status: TaskStatus = "queued"
    progress: TaskProgress = Field(default_factory=TaskProgress)
    error: str = ""
    chapter: int | None = None
    section_no: int | None = None
    result_title: str = ""
    result_word_count: int = 0
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""

    @staticmethod
    def now_iso() -> str:
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"
