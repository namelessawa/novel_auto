"""TickRuntime registry / switch_novel 联动测试 (v2.26 multi-tenant 重写).

旧版用模块级 _runtime 单例 + 单参 get_runtime("novel_a"); v2.26 改成
(user_id, novel_id) → TickRuntime 映射。本测试覆盖新注册表语义:
- get_runtime((user, novel)) 缓存
- set_active_novel(user, novel) 切换
- close_all_runtimes 清空注册表
- 多用户隔离 (同 novel_id 不同 user → 不同 runtime)
"""

from __future__ import annotations

import os
import tempfile

import pytest

import novel_manager
import tick_runtime


@pytest.fixture
def isolated_runtimes(monkeypatch):
    """v2.26 — 隔离 _DATA_ROOT/_USERS_ROOT + 清空注册表 (含 SQLite 句柄释放)."""
    td = tempfile.mkdtemp()
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", td)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", os.path.join(td, "users"))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", os.path.join(td, "novels")
    )
    # setup: 先释放任何残留连接再清字典 (Windows 防句柄泄漏)
    for rt in list(tick_runtime._runtimes.values()):
        try:
            rt.tick_db.close()
        except Exception:
            pass
    tick_runtime._clear_for_tests()

    yield

    # teardown: 同样先释放再清
    for rt in list(tick_runtime._runtimes.values()):
        try:
            rt.tick_db.close()
        except Exception:
            pass
    tick_runtime._clear_for_tests()


def _create_novel(user_id: str, title: str = "测试") -> str:
    """创建一个 novel 并返回 novel_id (供 get_runtime 用)."""
    entry = novel_manager.create_novel(user_id, title)
    return entry["id"]


def test_get_runtime_caches_per_novel(isolated_runtimes) -> None:
    """同一个 (user, novel) 多次 get_runtime → 同一实例; 不同 novel → 不同实例。"""
    user_id = "alice"
    n1 = _create_novel(user_id, "A1")
    n2 = _create_novel(user_id, "A2")

    a1 = tick_runtime.get_runtime(user_id, n1)
    a2 = tick_runtime.get_runtime(user_id, n1)
    b = tick_runtime.get_runtime(user_id, n2)

    assert a1 is a2
    assert a1 is not b
    assert a1.novel_id == n1
    assert b.novel_id == n2
    assert a1.data_dir != b.data_dir


def test_first_get_sets_active(isolated_runtimes) -> None:
    """第一次 get_runtime 应当把它注册为该用户的 active。"""
    user_id = "bob"
    n = _create_novel(user_id, "B1")
    assert tick_runtime.get_active_runtime(user_id) is None

    rt = tick_runtime.get_runtime(user_id, n)
    assert tick_runtime.get_active_runtime(user_id) is rt


def test_set_active_novel_swaps(isolated_runtimes) -> None:
    """set_active_novel(user, B) 之后, get_active_runtime(user) 必须返回 B。"""
    user_id = "carol"
    n_a = _create_novel(user_id, "A")
    n_b = _create_novel(user_id, "B")

    rt_a = tick_runtime.get_runtime(user_id, n_a)
    assert tick_runtime.get_active_runtime(user_id) is rt_a

    rt_b = tick_runtime.set_active_novel(user_id, n_b)
    assert tick_runtime.get_active_runtime(user_id) is rt_b

    tick_runtime.set_active_novel(user_id, n_a)
    assert tick_runtime.get_active_runtime(user_id) is rt_a


def test_set_active_novel_validates(isolated_runtimes) -> None:
    """非法 novel_id 必须被拒绝, 不能创建空字符串目录。"""
    with pytest.raises(ValueError):
        tick_runtime.set_active_novel("u", "")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        tick_runtime.set_active_novel("u", None)  # type: ignore[arg-type]


def test_independent_tick_state_per_novel(isolated_runtimes) -> None:
    """两本小说各自推进 tick → tick_state 完全隔离。"""
    user_id = "dave"
    n_a = _create_novel(user_id, "X")
    n_b = _create_novel(user_id, "Y")
    rt_a = tick_runtime.get_runtime(user_id, n_a)
    rt_b = tick_runtime.get_runtime(user_id, n_b)

    for _ in range(5):
        rt_a.tick_state.advance_tick()
    assert rt_a.tick_state.current_tick == 5
    assert rt_b.tick_state.current_tick == 0

    for _ in range(3):
        rt_b.tick_state.advance_tick()
    assert rt_a.tick_state.current_tick == 5
    assert rt_b.tick_state.current_tick == 3


def test_users_are_isolated(isolated_runtimes) -> None:
    """v2.26 关键 — 同 novel_id 不同 user 是两个独立 runtime。"""
    n_alice = _create_novel("alice", "shared_title")
    n_bob = _create_novel("bob", "shared_title")
    # 若 _slugify 给相同标题相同 id, 两 user 仍隔离
    rt_a = tick_runtime.get_runtime("alice", n_alice)
    rt_b = tick_runtime.get_runtime("bob", n_bob)
    assert rt_a is not rt_b
    # 同 user 不同活跃指针
    assert tick_runtime.get_active_runtime("alice") is rt_a
    assert tick_runtime.get_active_runtime("bob") is rt_b


def test_close_all_runtimes_clears_registry(isolated_runtimes) -> None:
    user_id = "eve"
    n_a = _create_novel(user_id, "A")
    n_b = _create_novel(user_id, "B")
    tick_runtime.get_runtime(user_id, n_a)
    tick_runtime.get_runtime(user_id, n_b)
    assert tick_runtime.get_active_runtime(user_id) is not None

    tick_runtime.close_all_runtimes()
    assert tick_runtime.get_active_runtime(user_id) is None
    # 重新 get 会构造新实例
    rt = tick_runtime.get_runtime(user_id, n_a)
    assert rt is not None
