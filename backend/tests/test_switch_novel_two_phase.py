"""POST /api/novels/{id}/switch 两阶段切换 (v2.26 multi-tenant).

回归 P1:此前先切 legacy pipeline、再 set_active_novel(tick); tick 失败
仅 warning 然后 return 200, UI 看到"切换成功"但 /api/tick/* 仍指向旧 novel,
状态分歧难诊断。

新顺序:
1. tick 先切 — 失败立刻 503, legacy 还停在旧 novel (一致状态)
2. tick 成功后再切 legacy

v2.26 — 加了 user_id 命名空间, 测试需要伪造 current_user。
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import routes
from auth import get_current_user
from auth.models import User


def _fake_user(uid="u1"):
    return User(
        id=uid,
        email=f"{uid}@local",
        has_password=False,
        save_my_works=True,
        created_at=datetime.fromtimestamp(0, tz=timezone.utc),
    )


@pytest.fixture
def client(monkeypatch, tmp_path):
    """构造最小 FastAPI 应用 + 桩 novel_manager / tick_runtime。"""

    # v2.26 — get_novel / get_novel_data_dir 都是 (user_id, novel_id) 签名
    monkeypatch.setattr(
        routes.novel_manager,
        "get_novel",
        lambda uid, nid: {"id": nid, "title": f"《{nid}》"}
        if nid != "missing" else None,
    )
    monkeypatch.setattr(
        routes.novel_manager,
        "get_novel_data_dir",
        lambda uid, nid: str(tmp_path / uid / nid),
    )
    monkeypatch.setattr(
        routes.novel_manager,
        "touch_last_accessed",
        lambda uid, nid: None,
    )

    class _StubPipe:
        def __init__(self, data_dir):
            self.data_dir = data_dir

        def save_state(self):
            pass

        def load_state(self):
            pass

    monkeypatch.setattr(routes, "GenerationPipeline", _StubPipe)

    # 重置全局 — 设置 u1 的 active 是 old_novel
    routes._pipelines.clear()
    routes._active_by_user.clear()
    routes._active_by_user["u1"] = "old_novel"

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def _install_tick_runtime_stub(monkeypatch, *, succeed: bool):
    """把 sys.modules['tick_runtime'] 替换为同步桩, 让 lazy import 命中它。"""
    mod = types.ModuleType("tick_runtime")

    if succeed:
        def set_active_novel(user_id: str, novel_id: str) -> None:
            mod.last_switched = (user_id, novel_id)
        mod.last_switched = None
    else:
        def set_active_novel(user_id: str, novel_id: str) -> None:
            raise RuntimeError(f"simulated tick failure for {novel_id}")

    mod.set_active_novel = set_active_novel
    monkeypatch.setitem(sys.modules, "tick_runtime", mod)
    return mod


def test_switch_succeeds_when_tick_runtime_ok(client, monkeypatch):
    tick_mod = _install_tick_runtime_stub(monkeypatch, succeed=True)

    resp = client.post("/api/novels/new_novel/switch")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["active_id"] == "new_novel"
    # tick 实际切了
    assert tick_mod.last_switched == ("u1", "new_novel")
    # legacy 也切了
    assert routes._active_by_user.get("u1") == "new_novel"
    assert routes._pipelines.get(("u1", "new_novel")) is not None


def test_switch_returns_503_when_tick_runtime_fails(client, monkeypatch):
    """tick 切换失败 → 503; legacy 状态保持旧 novel。"""
    _install_tick_runtime_stub(monkeypatch, succeed=False)

    resp = client.post("/api/novels/new_novel/switch")
    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert "tick runtime 切换失败" in body["detail"]
    # legacy 仍指向旧 novel
    assert routes._active_by_user.get("u1") == "old_novel"
    # 新 pipeline 未被构造
    assert ("u1", "new_novel") not in routes._pipelines


def test_switch_404_for_missing_novel(client, monkeypatch):
    """tick 桩存在但 novel_manager 返回 None — 404, 不进 tick 切换路径。"""
    tick_mod = _install_tick_runtime_stub(monkeypatch, succeed=True)
    resp = client.post("/api/novels/missing/switch")
    assert resp.status_code == 404
    # tick 不应被触动
    assert tick_mod.last_switched is None
