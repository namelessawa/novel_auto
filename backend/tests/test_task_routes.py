"""v2.37 — /api/tasks ownership 校验回归。

修复点: _check_ownership 此前是 ``if task.user_id and task.user_id != user_id``
— user_id=="" 的任务对任何登录用户可见/可取消。现在严格比较, 空 user_id 的
遗留任务对所有用户 404 (期望行为; 所有 create_task 调用点均强制传 user_id)。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from auth.models import User
from tasks.task_manager import _TaskRecord, get_task_manager
from tasks.task_models import Task
from tasks.task_routes import router


def _user(uid: str = "u1") -> User:
    return User(
        id=uid,
        email=f"{uid}@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


def _seed_task(mgr, task_id: str, user_id: str) -> Task:
    """直接塞一条终态任务记录 — 不经 create_task (它强制 user_id 入参,
    本测试恰恰要构造空 user_id 的遗留形态)。"""
    snap = Task(
        id=task_id,
        user_id=user_id,
        novel_id="nv1",
        kind="section_generation",
        status="completed",
        created_at=Task.now_iso(),
    )
    mgr._records[task_id] = _TaskRecord(snap)
    return snap


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _user("u1")
    mgr = get_task_manager()
    mgr._clear_for_tests()
    yield TestClient(app), mgr
    mgr._clear_for_tests()
    app.dependency_overrides.clear()


def test_own_task_visible(client) -> None:
    c, mgr = client
    _seed_task(mgr, "task_mine", "u1")
    r = c.get("/api/tasks/task_mine")
    assert r.status_code == 200
    assert r.json()["user_id"] == "u1"


def test_other_users_task_404(client) -> None:
    c, mgr = client
    _seed_task(mgr, "task_bob", "bob")
    assert c.get("/api/tasks/task_bob").status_code == 404


def test_empty_user_id_task_404_for_everyone(client) -> None:
    """核心回归 — user_id=="" 不再是任意用户可访问的后门。"""
    c, mgr = client
    _seed_task(mgr, "task_legacy", "")
    assert c.get("/api/tasks/task_legacy").status_code == 404


def test_empty_user_id_task_cannot_be_cancelled(client) -> None:
    c, mgr = client
    _seed_task(mgr, "task_legacy2", "")
    assert c.post("/api/tasks/task_legacy2/cancel").status_code == 404


def test_list_only_returns_own_tasks(client) -> None:
    c, mgr = client
    _seed_task(mgr, "t_u1", "u1")
    _seed_task(mgr, "t_bob", "bob")
    _seed_task(mgr, "t_empty", "")
    body = c.get("/api/tasks").json()
    assert body["count"] == 1
    assert body["tasks"][0]["id"] == "t_u1"
