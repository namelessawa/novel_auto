"""TickRuntime registry / switch_novel 联动测试 (v2.15)。

旧实现是模块级 _runtime 单例 → switch_novel 只换 legacy pipeline,
/api/tick/* 永远绑在启动时那本小说。

新实现:
- get_runtime(novel_id) 按需构造并缓存
- set_active_novel(novel_id) 切换路由层指向的 runtime
- close_all_runtimes 清空注册表
"""

from __future__ import annotations

import os

import pytest

import tick_runtime
from api.tick_routes import _container


@pytest.fixture
def isolated_runtimes(tmp_path, monkeypatch):
    """让 TickRuntime 写到 tmp_path, 并在测试前后清空注册表。"""

    def fake_resolve(novel_id: str | None = None) -> str:
        nid = novel_id or "default"
        path = tmp_path / "novels" / nid
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    monkeypatch.setattr(tick_runtime, "_resolve_novel_data_dir", fake_resolve)
    tick_runtime._clear_for_tests()
    # 路由容器也清掉, 防上层泄漏
    _container.orchestrator = None
    _container.tick_state = None
    _container.tick_db = None

    yield

    # cleanup — 关闭所有以释放 sqlite 文件句柄, 否则 Windows tmp 清理会报错
    tick_runtime.close_all_runtimes()
    _container.orchestrator = None
    _container.tick_state = None
    _container.tick_db = None


def test_get_runtime_caches_per_novel(isolated_runtimes) -> None:
    """同一个 novel_id 多次 get_runtime → 同一实例; 不同 novel_id → 不同实例。"""
    a1 = tick_runtime.get_runtime("novel_a")
    a2 = tick_runtime.get_runtime("novel_a")
    b = tick_runtime.get_runtime("novel_b")

    assert a1 is a2
    assert a1 is not b
    assert a1.novel_id == "novel_a"
    assert b.novel_id == "novel_b"
    # data_dir 真正独立 — 防止两个 runtime 写同一目录
    assert a1.data_dir != b.data_dir


def test_first_get_sets_active_and_registers_routes(isolated_runtimes) -> None:
    """第一次 get_runtime 应当把它注册为 active 并注入路由容器。"""
    assert tick_runtime.get_active_runtime() is None
    assert _container.orchestrator is None

    rt = tick_runtime.get_runtime("novel_a")
    assert tick_runtime.get_active_runtime() is rt
    assert _container.orchestrator is rt.orchestrator
    assert _container.tick_state is rt.tick_state


def test_set_active_novel_swaps_routes_container(isolated_runtimes) -> None:
    """set_active_novel('B') 之后, tick_routes 容器必须指向 B 的 orchestrator。"""
    rt_a = tick_runtime.get_runtime("novel_a")
    assert _container.orchestrator is rt_a.orchestrator

    rt_b = tick_runtime.set_active_novel("novel_b")
    assert _container.orchestrator is rt_b.orchestrator
    assert _container.tick_state is rt_b.tick_state
    assert tick_runtime.get_active_runtime() is rt_b

    # 再切回 A
    tick_runtime.set_active_novel("novel_a")
    assert _container.orchestrator is rt_a.orchestrator


def test_set_active_novel_validates(isolated_runtimes) -> None:
    """非法 novel_id 必须被拒绝, 不能创建空字符串目录。"""
    with pytest.raises(ValueError):
        tick_runtime.set_active_novel("")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        tick_runtime.set_active_novel(None)  # type: ignore[arg-type]


def test_independent_tick_state_per_novel(isolated_runtimes) -> None:
    """两本小说各自推进 tick → tick_state 完全隔离。"""
    rt_a = tick_runtime.get_runtime("novel_a")
    rt_b = tick_runtime.get_runtime("novel_b")

    # 模拟 A 推了 5 个 tick
    for _ in range(5):
        rt_a.tick_state.advance_tick()
    # B 没动
    assert rt_a.tick_state.current_tick == 5
    assert rt_b.tick_state.current_tick == 0

    # B 推 3 tick
    for _ in range(3):
        rt_b.tick_state.advance_tick()
    assert rt_a.tick_state.current_tick == 5
    assert rt_b.tick_state.current_tick == 3


def test_close_all_runtimes_clears_registry(isolated_runtimes) -> None:
    tick_runtime.get_runtime("novel_a")
    tick_runtime.get_runtime("novel_b")
    assert tick_runtime.get_active_runtime() is not None

    tick_runtime.close_all_runtimes()
    assert tick_runtime.get_active_runtime() is None
    # 重新 get 会构造新实例
    rt = tick_runtime.get_runtime("novel_a")
    assert rt is not None
