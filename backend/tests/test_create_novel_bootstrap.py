"""v2.24 — create_novel 自动入队 bootstrap_section 任务 (v2.26 multi-tenant 重写)."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from datetime import datetime, timezone

import pytest

from auth.models import User


def _fake_user(user_id: str = "test_user") -> User:
    return User(
        id=user_id,
        email=f"{user_id}@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


@pytest.fixture
def tmp_novels_root(monkeypatch):
    """v2.26 — 把 novel_manager._DATA_ROOT / _USERS_ROOT 重定向到临时目录."""
    tmp = tempfile.mkdtemp(prefix="nv_test_")
    import novel_manager

    monkeypatch.setattr(novel_manager, "_DATA_ROOT", tmp)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", os.path.join(tmp, "users"))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", os.path.join(tmp, "novels")
    )
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def isolate_runtime_and_stores(monkeypatch, tmp_novels_root):
    """让 tick_runtime + section_store + task_manager 都用隔离状态。"""
    from tasks.task_manager import get_task_manager
    get_task_manager()._clear_for_tests()

    from sections import section_store as _ss
    _ss._stores.clear()

    import tick_runtime
    tick_runtime._clear_for_tests()

    # tick_runtime.get_runtime: fake 返回不会真跑的 runtime, 避免触发实际 LLM
    class _FakeOrch:
        current_tick = 0
        last_narrator_output = None

        async def run_tick(self):
            class _S:
                tick = 0
            return _S()

    class _FakeRuntime:
        def __init__(self, user_id, novel_id):
            self.user_id = user_id
            self.novel_id = novel_id
            self.orchestrator = _FakeOrch()

    runtimes: dict = {}

    def _fake_get_runtime(user_id, novel_id=None):
        nid = novel_id or "default"
        key = (user_id, nid)
        if key not in runtimes:
            runtimes[key] = _FakeRuntime(user_id, nid)
        return runtimes[key]

    monkeypatch.setattr("tick_runtime.get_runtime", _fake_get_runtime)
    yield


# ---- 测试 -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_novel_default_skips_bootstrap_task_v225(
    isolate_runtime_and_stores, mock_llm
):
    """v2.25 默认 auto_bootstrap=False — POST /api/novels 仅创建空壳, 返回空 task_id。"""
    from api.routes import NovelCreateRequest, create_novel
    from tasks.task_manager import get_task_manager

    user = _fake_user("u_default")
    resp = await create_novel(
        NovelCreateRequest(title="测试小说 A"), current_user=user
    )
    assert resp["title"] == "测试小说 A"
    assert resp["bootstrap_task_id"] == ""
    mgr = get_task_manager()
    assert mgr.list_for_user_and_novel(user.id, resp["id"]) == []


@pytest.mark.asyncio
async def test_create_novel_with_auto_bootstrap_true_still_spawns_task(
    isolate_runtime_and_stores, mock_llm
):
    """显式 ?auto_bootstrap=true 仍走 v2.24 路径 — 保留供测试 / 节级管线对照实验。"""
    from api.routes import NovelCreateRequest, create_novel
    from tasks.task_manager import get_task_manager

    user = _fake_user("u_auto")
    mock_llm.set_responses(["首节" for _ in range(5)])
    resp = await create_novel(
        NovelCreateRequest(title="测试小说 B"),
        auto_bootstrap=True,
        current_user=user,
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

    def _boom(user_id, novel_id=None):
        raise RuntimeError("runtime 挂了")

    monkeypatch.setattr("tick_runtime.get_runtime", _boom)

    user = _fake_user("u_fail")
    resp = await create_novel(
        NovelCreateRequest(title="测试小说 C"),
        auto_bootstrap=True,
        current_user=user,
    )
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
    ):
        assert path in paths, f"路由未注册: {path}"
