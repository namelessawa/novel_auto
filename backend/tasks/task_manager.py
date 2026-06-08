"""v2.24 任务管理器 — 后台异步任务的注册、生命周期、SSE 流。

设计要点
--------
* **跨小说并行**: novel A 跑 section_generation 时 novel B 也能跑各自的;
  同一 novel + 同一 kind 同时只允许一个 (409 由 ``create_task`` 抛)。
* **进度推送**: 每个 task 持有一个 ``asyncio.Event``, executor 通过
  ``ProgressUpdater`` 调用 ``set_progress`` 触发事件 — SSE 处理器以
  "等待事件 → yield 最新快照" 的循环订阅, 无队列, 无 memory leak。
* **取消语义**: ``cancel(task_id)`` 调用底层 asyncio.Task.cancel(),
  executor 内部应捕获 CancelledError 做清理。
* **不可变快照**: Task 是 Pydantic 模型, 每次更新通过 ``model_copy(update=...)``
  生成新副本, 避免 SSE 推送时被并发修改。
* **持久化**: 当前不持久化任务 — 进程重启即清空。续写任务的实际效果 (Section
  文本) 由 SectionCloser 落盘到 narratives/ 或 sections.jsonl, 不依赖 Task 本体。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from tasks.task_models import Task, TaskKind, TaskProgress, TaskStatus

logger = logging.getLogger(__name__)


class TaskConflict(Exception):
    """同 novel + 同 kind 已在 running/queued 状态 — 调用方应返回 409。"""


class TaskNotFound(Exception):
    """task_id 不存在 — 调用方应返回 404。"""


class ProgressUpdater:
    """传给 executor 的回调对象, 用于更新进度。

    设计为对象而非裸函数, 因为 executor 内部多处更新进度, 每处构造一个
    完整字典累赘; 让 updater 持有 task_id + 引用即可。
    """

    def __init__(self, manager: "TaskManager", task_id: str) -> None:
        self._manager = manager
        self._task_id = task_id

    def set(
        self,
        *,
        current_words: int | None = None,
        tick_count: int | None = None,
        current_tick: int | None = None,
        last_message: str | None = None,
    ) -> None:
        self._manager._update_progress(
            self._task_id,
            current_words=current_words,
            tick_count=tick_count,
            current_tick=current_tick,
            last_message=last_message,
        )


# Executor 签名: (updater, user_id, novel_id) → 最终结果 dict (会合并进 Task.result_*)。
# 必须可取消 — 内部应捕获 CancelledError 做清理后再 raise。
# v2.26 — 第 2 参数从 novel_id 改为 (user_id, novel_id) 两个位置参数。
Executor = Callable[[ProgressUpdater, str, str], Awaitable[dict[str, Any]]]


class _TaskRecord:
    """内部记录 — 把 Task 快照、asyncio.Task、更新事件捆在一起。"""

    __slots__ = ("snapshot", "asyncio_task", "update_event")

    def __init__(self, snapshot: Task) -> None:
        self.snapshot = snapshot
        self.asyncio_task: asyncio.Task | None = None
        self.update_event = asyncio.Event()


class TaskManager:
    """单例 — 由 get_task_manager() 取得, 不要直接实例化。"""

    def __init__(self) -> None:
        self._records: dict[str, _TaskRecord] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 创建 / 查询
    # ------------------------------------------------------------------

    async def create_task(
        self,
        *,
        user_id: str,
        novel_id: str,
        novel_title: str,
        kind: TaskKind,
        executor: Executor,
        target_words: int,
        min_words: int,
        max_ticks: int,
        chapter: int | None = None,
        section_no: int | None = None,
    ) -> Task:
        """创建并立即启动一个后台任务。

        v2.26 — ``user_id`` 必填。同 user + 同 novel + 同 kind 已存在
        running/queued 时抛 TaskConflict (路由层转 409)。跨用户的同 novel_id
        不冲突 (multi-tenant 命名空间已隔离)。
        """
        async with self._lock:
            for rec in self._records.values():
                snap = rec.snapshot
                if (
                    snap.user_id == user_id
                    and snap.novel_id == novel_id
                    and snap.kind == kind
                    and snap.status in ("queued", "running")
                ):
                    raise TaskConflict(
                        f"novel {novel_id!r} 已有 {kind} 任务 {snap.id} 处于 {snap.status}"
                    )

            task_id = f"task_{uuid.uuid4().hex[:12]}"
            now = Task.now_iso()
            snapshot = Task(
                id=task_id,
                user_id=user_id,
                novel_id=novel_id,
                novel_title=novel_title,
                kind=kind,
                status="queued",
                progress=TaskProgress(
                    target_words=target_words,
                    min_words=min_words,
                    max_ticks=max_ticks,
                ),
                chapter=chapter,
                section_no=section_no,
                created_at=now,
            )
            record = _TaskRecord(snapshot)
            self._records[task_id] = record

        # 启动 asyncio task — 不放在 lock 内, 避免 executor 调 update 时死锁
        record.asyncio_task = asyncio.create_task(
            self._run(task_id, executor, user_id, novel_id),
            name=f"task-{task_id}",
        )
        return record.snapshot

    def get(self, task_id: str) -> Task:
        rec = self._records.get(task_id)
        if rec is None:
            raise TaskNotFound(task_id)
        return rec.snapshot

    def list_all(self) -> list[Task]:
        return [r.snapshot for r in self._records.values()]

    def list_for_novel(self, novel_id: str) -> list[Task]:
        return [r.snapshot for r in self._records.values() if r.snapshot.novel_id == novel_id]

    def list_for_user(self, user_id: str) -> list[Task]:
        """v2.26 — 仅返回该用户的任务 (含历史/终态)。"""
        return [r.snapshot for r in self._records.values() if r.snapshot.user_id == user_id]

    def list_for_user_and_novel(self, user_id: str, novel_id: str) -> list[Task]:
        return [
            r.snapshot
            for r in self._records.values()
            if r.snapshot.user_id == user_id and r.snapshot.novel_id == novel_id
        ]

    # ------------------------------------------------------------------
    # 取消
    # ------------------------------------------------------------------

    async def cancel(self, task_id: str) -> Task:
        rec = self._records.get(task_id)
        if rec is None:
            raise TaskNotFound(task_id)
        if rec.snapshot.status in ("completed", "failed", "cancelled"):
            return rec.snapshot
        if rec.asyncio_task is not None and not rec.asyncio_task.done():
            rec.asyncio_task.cancel()
        # 实际状态切换由 _run 的 CancelledError 分支处理
        return rec.snapshot

    # ------------------------------------------------------------------
    # SSE 订阅
    # ------------------------------------------------------------------

    async def watch(self, task_id: str) -> AsyncIterator[Task]:
        """对单个 task 的进度做无限订阅。终态后立即 break。"""
        rec = self._records.get(task_id)
        if rec is None:
            raise TaskNotFound(task_id)
        # 先 yield 当前状态, 让订阅者拿到初始快照
        yield rec.snapshot
        while True:
            if rec.snapshot.status in ("completed", "failed", "cancelled"):
                return
            await rec.update_event.wait()
            rec.update_event.clear()
            yield rec.snapshot

    # ------------------------------------------------------------------
    # 内部 — executor 包装
    # ------------------------------------------------------------------

    async def _run(
        self, task_id: str, executor: Executor, user_id: str, novel_id: str
    ) -> None:
        rec = self._records.get(task_id)
        if rec is None:
            logger.error("_run: task %s vanished before start", task_id)
            return

        self._set_status(task_id, "running", started_at=Task.now_iso())
        updater = ProgressUpdater(self, task_id)
        try:
            result = await executor(updater, user_id, novel_id)
            self._mark_completed(task_id, result)
        except asyncio.CancelledError:
            logger.info("Task %s cancelled", task_id)
            self._set_status(
                task_id,
                "cancelled",
                completed_at=Task.now_iso(),
                error="任务已取消",
            )
            # 不 re-raise — 已被 cancel() 标记, 主循环不需要异常传播
        except Exception as e:
            logger.exception("Task %s failed: %s", task_id, e)
            self._set_status(
                task_id,
                "failed",
                completed_at=Task.now_iso(),
                error=f"{type(e).__name__}: {e}",
            )

    def _mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        rec = self._records.get(task_id)
        if rec is None:
            return
        update: dict[str, Any] = {
            "status": "completed",
            "completed_at": Task.now_iso(),
        }
        if "result_title" in result:
            update["result_title"] = str(result["result_title"])
        if "result_word_count" in result:
            update["result_word_count"] = int(result["result_word_count"])
        if "chapter" in result and result["chapter"] is not None:
            update["chapter"] = int(result["chapter"])
        if "section_no" in result and result["section_no"] is not None:
            update["section_no"] = int(result["section_no"])
        rec.snapshot = rec.snapshot.model_copy(update=update)
        rec.update_event.set()

    def _set_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        started_at: str = "",
        completed_at: str = "",
        error: str = "",
    ) -> None:
        rec = self._records.get(task_id)
        if rec is None:
            return
        update: dict[str, Any] = {"status": status}
        if started_at:
            update["started_at"] = started_at
        if completed_at:
            update["completed_at"] = completed_at
        if error:
            update["error"] = error
        rec.snapshot = rec.snapshot.model_copy(update=update)
        rec.update_event.set()

    def _update_progress(
        self,
        task_id: str,
        *,
        current_words: int | None,
        tick_count: int | None,
        current_tick: int | None,
        last_message: str | None,
    ) -> None:
        rec = self._records.get(task_id)
        if rec is None:
            return
        prog_update: dict[str, Any] = {}
        if current_words is not None:
            prog_update["current_words"] = current_words
        if tick_count is not None:
            prog_update["tick_count"] = tick_count
        if current_tick is not None:
            prog_update["current_tick"] = current_tick
        if last_message is not None:
            prog_update["last_message"] = last_message
        if not prog_update:
            return
        new_progress = rec.snapshot.progress.model_copy(update=prog_update)
        rec.snapshot = rec.snapshot.model_copy(update={"progress": new_progress})
        rec.update_event.set()

    # ------------------------------------------------------------------
    # 测试钩子
    # ------------------------------------------------------------------

    def _clear_for_tests(self) -> None:
        """清空注册表 — 仅供 pytest 用, 不取消 in-flight asyncio.Task。"""
        self._records.clear()


# 模块级单例
_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    global _manager
    if _manager is None:
        _manager = TaskManager()
    return _manager
