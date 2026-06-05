"""v2.24 — create_novel 自动入队 bootstrap_section 任务。"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

import pytest


@pytest.fixture
def tmp_novels_root(monkeypatch):
    """把 novel_manager._NOVELS_DIR 重定向到临时目录, 隔离全局 manifest。"""
    tmp = tempfile.mkdtemp(prefix="nv_test_")
    import novel_manager

    monkeypatch.setattr(novel_manager, "_NOVELS_DIR", tmp)
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def isolate_runtime_and_stores(monkeypatch, tmp_novels_root):
    """让 tick_runtime + section_store + task_manager 都用隔离状态。"""
    # 重置 task manager
    from tasks.task_manager import get_task_manager
    get_task_manager()._clear_for_tests()

    # 重置 section store registry
    from sections import section_store as _ss
    _ss._stores.clear()

    # tick_runtime: 改成"返回不会真跑的 fake runtime", 避免触发实际 LLM
    class _FakeOrch:
        current_tick = 0
        last_narrator_output = None

        async def run_tick(self):
            class _S:
                tick = 0
            return _S()

    class _FakeRuntime:
        def __init__(self, novel_id):
            self.orchestrator = _FakeOrch()

    runtimes: dict = {}

    def _fake_get_runtime(novel_id=None):
        nid = novel_id or "default"
        if nid not in runtimes:
            runtimes[nid] = _FakeRuntime(nid)
        return runtimes[nid]

    monkeypatch.setattr("tick_runtime.get_runtime", _fake_get_runtime)
    monkeypatch.setattr("api.routes.novel_manager", __import__("novel_manager"))
    yield


# ---- 测试 -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_novel_default_skips_bootstrap_task_v225(
    isolate_runtime_and_stores, mock_llm
):
    """v2.25 默认 auto_bootstrap=False — POST /api/novels 仅创建空壳, 返回空 task_id。

    v2.24 默认是 True, v2.25 反转: fresh novel 没种子 → 自动入 bootstrap_section
    会产出空首节; 让前端显式走 bootstrap-world 端点。
    """
    from api.routes import NovelCreateRequest, create_novel
    from tasks.task_manager import get_task_manager

    resp = await create_novel(NovelCreateRequest(title="测试小说 A"))
    assert resp["title"] == "测试小说 A"
    assert resp["bootstrap_task_id"] == ""
    mgr = get_task_manager()
    assert mgr.list_for_novel(resp["id"]) == []


@pytest.mark.asyncio
async def test_create_novel_with_auto_bootstrap_true_still_spawns_task(
    isolate_runtime_and_stores, mock_llm
):
    """显式 ?auto_bootstrap=true 仍走 v2.24 路径 — 保留供测试 / 节级管线对照实验。"""
    from api.routes import NovelCreateRequest, create_novel
    from tasks.task_manager import get_task_manager

    mock_llm.set_responses(["首节" for _ in range(5)])
    resp = await create_novel(
        NovelCreateRequest(title="测试小说 B"), auto_bootstrap=True
    )
    assert resp["title"] == "测试小说 B"
    assert resp["bootstrap_task_id"], "显式 auto_bootstrap=True 时应返回非空 task_id"

    mgr = get_task_manager()
    snap = mgr.get(resp["bootstrap_task_id"])
    assert snap.kind == "bootstrap_section"
    assert snap.novel_id == resp["id"]


@pytest.mark.asyncio
async def test_bootstrap_failure_does_not_break_novel_creation(
    isolate_runtime_and_stores, mock_llm, monkeypatch
):
    """bootstrap 失败 (runtime init 抛) 时 novel 仍创建, task_id 空。"""
    from api.routes import NovelCreateRequest, create_novel

    def _boom(novel_id=None):
        raise RuntimeError("runtime 挂了")

    # _spawn_bootstrap_section_task 内部走 inline `from tick_runtime import get_runtime`,
    # 所以补丁 tick_runtime.get_runtime 即可 — 函数级 import 在调用时解析模块属性。
    monkeypatch.setattr("tick_runtime.get_runtime", _boom)

    resp = await create_novel(NovelCreateRequest(title="测试小说 C"))
    assert resp["title"] == "测试小说 C"
    assert resp["bootstrap_task_id"] == ""


@pytest.mark.asyncio
async def test_legacy_alias_routes_registered():
    """/api/legacy/generate 等别名应当被 FastAPI 注册。"""
    import main

    paths = {getattr(r, "path", "") for r in main.app.routes}
    for path in (
        "/api/legacy/generate",
        "/api/legacy/generate/stream",
        "/api/legacy/chapter/advance",
        "/api/legacy/rollback",
        "/api/legacy/snapshots",
        "/api/legacy/reset",
    ):
        assert path in paths, f"路由未注册: {path}"
