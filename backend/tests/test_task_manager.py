"""v2.24 任务管理器 — 生命周期 / 并发 / 取消 / SSE 订阅。"""

from __future__ import annotations

import asyncio

import pytest

from tasks.task_manager import (
    ProgressUpdater,
    TaskConflict,
    TaskManager,
    TaskNotFound,
)


@pytest.fixture
def manager():
    m = TaskManager()
    yield m
    m._clear_for_tests()


# ---- 基本生命周期 -----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_runs_executor_and_marks_completed(manager):
    seen: dict = {}

    async def executor(updater: ProgressUpdater, novel_id: str):
        seen["novel_id"] = novel_id
        updater.set(current_words=100, tick_count=1)
        return {"result_title": "完成", "result_word_count": 100}

    snap = await manager.create_task(
        novel_id="nv1",
        novel_title="测试",
        kind="section_generation",
        executor=executor,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    # 等待 background task 跑完
    await asyncio.sleep(0.05)
    final = manager.get(snap.id)
    assert final.status == "completed"
    assert final.result_title == "完成"
    assert final.result_word_count == 100
    assert final.progress.current_words == 100
    assert seen["novel_id"] == "nv1"


@pytest.mark.asyncio
async def test_executor_raises_marks_failed(manager):
    async def boom(updater, novel_id):
        raise RuntimeError("LLM 挂了")

    snap = await manager.create_task(
        novel_id="nv1",
        novel_title="",
        kind="section_generation",
        executor=boom,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    await asyncio.sleep(0.05)
    final = manager.get(snap.id)
    assert final.status == "failed"
    assert "RuntimeError" in final.error
    assert "LLM 挂了" in final.error


# ---- 并发约束 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_novel_same_kind_conflict(manager):
    async def slow(updater, novel_id):
        await asyncio.sleep(0.2)
        return {}

    await manager.create_task(
        novel_id="nv1",
        novel_title="",
        kind="section_generation",
        executor=slow,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    with pytest.raises(TaskConflict):
        await manager.create_task(
            novel_id="nv1",
            novel_title="",
            kind="section_generation",
            executor=slow,
            target_words=3000,
            min_words=2400,
            max_ticks=30,
        )


@pytest.mark.asyncio
async def test_different_novels_parallel_ok(manager):
    async def slow(updater, novel_id):
        await asyncio.sleep(0.1)
        return {}

    a = await manager.create_task(
        novel_id="nv1",
        novel_title="",
        kind="section_generation",
        executor=slow,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    b = await manager.create_task(
        novel_id="nv2",
        novel_title="",
        kind="section_generation",
        executor=slow,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    assert a.id != b.id
    # 两者在 running 或 queued
    assert manager.get(a.id).status in ("queued", "running")
    assert manager.get(b.id).status in ("queued", "running")


@pytest.mark.asyncio
async def test_completed_does_not_block_new_task(manager):
    async def fast(updater, novel_id):
        return {}

    a = await manager.create_task(
        novel_id="nv1",
        novel_title="",
        kind="section_generation",
        executor=fast,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    await asyncio.sleep(0.05)
    assert manager.get(a.id).status == "completed"

    # 同 novel 同 kind 再起一个 — 不应冲突
    b = await manager.create_task(
        novel_id="nv1",
        novel_title="",
        kind="section_generation",
        executor=fast,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    assert a.id != b.id


# ---- 取消 -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_in_flight_task(manager):
    async def slow(updater, novel_id):
        await asyncio.sleep(10)
        return {}

    snap = await manager.create_task(
        novel_id="nv1",
        novel_title="",
        kind="section_generation",
        executor=slow,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    await asyncio.sleep(0.02)
    await manager.cancel(snap.id)
    await asyncio.sleep(0.05)
    final = manager.get(snap.id)
    assert final.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_unknown_raises(manager):
    with pytest.raises(TaskNotFound):
        await manager.cancel("task_does_not_exist")


# ---- SSE 订阅 ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_watch_yields_initial_then_progress_then_terminal(manager):
    async def staged(updater, novel_id):
        await asyncio.sleep(0.02)
        updater.set(current_words=1000, tick_count=5)
        await asyncio.sleep(0.02)
        updater.set(current_words=2500, tick_count=12)
        return {"result_title": "完结", "result_word_count": 2500}

    snap = await manager.create_task(
        novel_id="nv1",
        novel_title="",
        kind="section_generation",
        executor=staged,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    seen_states: list = []
    async for s in manager.watch(snap.id):
        seen_states.append((s.status, s.progress.current_words))
        if s.status == "completed":
            break

    # 至少应见到初始 queued/running + 完成态
    assert seen_states[-1][0] == "completed"
    # 终态字数 = 2500 (executor 最后一次 set)
    assert seen_states[-1][1] == 2500


@pytest.mark.asyncio
async def test_watch_unknown_raises(manager):
    with pytest.raises(TaskNotFound):
        async for _ in manager.watch("nope"):
            pass


# ---- list 过滤 --------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_for_novel_filters(manager):
    async def fast(updater, novel_id):
        return {}

    await manager.create_task(
        novel_id="A",
        novel_title="",
        kind="section_generation",
        executor=fast,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    await manager.create_task(
        novel_id="B",
        novel_title="",
        kind="section_generation",
        executor=fast,
        target_words=3000,
        min_words=2400,
        max_ticks=30,
    )
    await asyncio.sleep(0.05)
    a_tasks = manager.list_for_novel("A")
    b_tasks = manager.list_for_novel("B")
    assert len(a_tasks) == 1 and a_tasks[0].novel_id == "A"
    assert len(b_tasks) == 1 and b_tasks[0].novel_id == "B"
    assert len(manager.list_all()) == 2
