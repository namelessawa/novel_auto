"""Regression: reload_cache / drop_cache 不得用 stale in-memory state 覆盖盘上数据。

Bug 复盘 (2026-06-09)
---------------------
bootstrap_world 跑完后, ``_reload_runtime`` 调当时叫 ``drop_runtime`` 的函数,
旧实现里 ``rt.close()`` 会把 cached runtime 的 in-memory TickState 原子写回盘
(``self.tick_state.save``) — 而该 in-memory 状态是 bootstrap **之前**
frontend 触发 ``set_active_novel`` 时构造的, 内容是空的。结果: bootstrap
刚写盘的 5 角色 / 5 地点 / 5 伏笔 / 4 风格锚点全被空覆盖, Narrator 跑
30 个 tick 后 tick_state.json 里只剩 ``era=初始纪元`` 和泛化的
``loc_wilderness``, 跟标题完全脱节。

v2.36 重构: 拆成 ``reload_cache`` (drop + 若 active 重建) 和 ``drop_cache``
(纯丢弃, cleanup_task 用) 两个明确语义。本测试覆盖:

1. reload_cache 保留盘上 4 个 disk artifact (tick_state / summary_tree / KG /
   character_profiles) 不被 stale state 覆盖
2. reload_cache 后 SQLite 文件锁释放 — 直接对 data_dir 调 shutil.rmtree 必须成功
3. drop_cache 不重建 runtime + 清掉 _active_by_user 指针 (cleanup_task 路径)
4. drop_runtime 别名仍正常 (向后兼容)
"""

from __future__ import annotations

import json
import os
import shutil

import pytest

import novel_manager
import tick_runtime
from memory.summary_tree import SummaryTree
from memory.tick_state import TickState
from memory_system.models import CharacterProfile, WorldState


@pytest.fixture
def tenant_root(tmp_path, monkeypatch):
    """把 novel_manager 的数据根重指向 tmp_path, 测试结束自动清理。

    Setup + teardown 对称: 都在清 registry 之前先关掉所有 SQLite 句柄, 防止
    上一个测试或本测试残留连接卡住 Windows tmp_path cleanup。
    """
    data_root = tmp_path / "data"
    users_root = data_root / "users"
    users_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", str(data_root))
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", str(users_root))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", str(data_root / "novels")
    )
    _close_and_clear_registry()
    yield
    _close_and_clear_registry()


def _close_and_clear_registry() -> None:
    """对称的 setup/teardown 工具 — 先释放所有 SQLite 句柄再清 dict, 防 Windows
    tmp_path 因被占用而 cleanup 失败。"""
    for rt in list(tick_runtime._runtimes.values()):
        try:
            rt.tick_db.close()
        except Exception:
            pass
    tick_runtime._clear_for_tests()


def _read_disk_state(data_dir: str) -> dict:
    with open(os.path.join(data_dir, "tick_state.json"), encoding="utf-8") as f:
        return json.load(f)


def _make_profile() -> CharacterProfile:
    """构造一个仅含必要字段的 CharacterProfile — 减少与未来 schema 变化的耦合。"""
    return CharacterProfile(
        id="char_aria",
        name="Aria",
        age=17,
        role="主角",
        importance_tier="A",
        personality="坚韧",
        appearance="蓝发",
        speech_style="简洁",
        core_values=["守护"],
        fears=["失去"],
        desires=["真相"],
    )


def test_reload_cache_preserves_externally_written_disk(tenant_root) -> None:
    """模拟 bootstrap 直写盘 → reload_cache → 盘上数据必须留下 (tick_state + KG + summary_tree)。"""
    user_id = "testuser"
    entry = novel_manager.create_novel(user_id, title="测试小说")
    novel_id = entry["id"]
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)

    # 1. frontend 进入小说页面, 构造 TickRuntime — 此时盘上无 tick_state.json,
    #    in-memory TickState 是默认空状态。
    rt = tick_runtime.get_runtime(user_id, novel_id)
    assert rt.tick_state.world_state.era == ""
    assert len(rt.tick_state.list_character_profiles()) == 0

    # 2. bootstrap_world 用独立 TickState 实例直写盘 (复刻真实路径)。
    fresh_ts = TickState(data_dir=data_dir)
    fresh_ts.set_world_state(WorldState(era="近未来魔法衰退纪元"))
    fresh_ts.upsert_character_profile(_make_profile())
    fresh_ts.save()

    # 同时直写 summary_tree.json (用 valid schema + sentinel merge_threshold,
    # 防止 rebuild 路径的 load_from_disk 把它 quarantine 掉)。这覆盖原 close() 路径
    # 中 SummaryTree.persist_to_disk 也会被 stale state 覆盖的回归面。
    summary_path = os.path.join(data_dir, "summary_tree.json")
    sentinel_tree = SummaryTree(merge_threshold=999)
    sentinel_tree.persist_to_disk(summary_path)

    # 3. bootstrap_routes._reload_runtime 调 reload_cache —
    #    旧实现会 rt.close() → 把 stale state save 回盘, 覆盖 bootstrap 数据。
    tick_runtime.reload_cache(user_id, novel_id)

    # 4. 两个 disk artifact 必须都是 bootstrap 内容, 不能被空覆盖。
    on_disk = _read_disk_state(data_dir)
    assert on_disk["world_state"]["era"] == "近未来魔法衰退纪元", (
        f"tick_state era 被 stale state 覆盖: {on_disk['world_state']!r}"
    )
    assert "char_aria" in on_disk["character_profiles"], (
        f"角色丢失: {list(on_disk['character_profiles'].keys())!r}"
    )

    # SummaryTree: 用 merge_threshold sentinel 验证 — 若 reload_cache 误调
    # persist_to_disk, 默认 merge_threshold=10 会覆盖我们写入的 999。
    with open(summary_path, encoding="utf-8") as f:
        on_disk_summary = json.load(f)
    assert on_disk_summary.get("merge_threshold") == 999, (
        f"summary_tree.json 被 stale persist 覆盖: merge_threshold="
        f"{on_disk_summary.get('merge_threshold')!r} (期望 999)"
    )

    # 5. reload 后重新 get — 新 runtime 必须从盘载入 bootstrap 数据 (非身份比对,
    #    身份不等是 reload_cache 主动重建保证的, 真正要证明的是 *state* 是从盘载入)。
    rt_after = tick_runtime.get_runtime(user_id, novel_id)
    assert rt_after.tick_state.world_state.era == "近未来魔法衰退纪元"
    assert rt_after.tick_state.get_character_profile("char_aria") is not None


def test_drop_cache_releases_sqlite_lock_for_rmtree(tenant_root) -> None:
    """cleanup_task 路径: drop_cache 后 shutil.rmtree(data_dir) 必须成功 — 验证
    SQLite 文件锁被真实释放 (Windows 下若锁未释放, rmtree(ignore_errors=True)
    会静默吞掉 PermissionError 留下孤儿目录, 这是 fix 的核心动机)。"""
    user_id = "cleanup_user"
    entry = novel_manager.create_novel(user_id, title="将被删除的小说")
    novel_id = entry["id"]
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)

    rt = tick_runtime.get_runtime(user_id, novel_id)
    # 模拟一次 tick_db 触发, 确保 ticks.db 被实际写入
    _ = rt.tick_db
    assert os.path.exists(os.path.join(data_dir, "ticks.db"))

    # drop_cache: 不重建, 不写盘
    tick_runtime.drop_cache(user_id, novel_id)

    # 注册表已清空, _active_by_user 指针已清, 不会自动重建
    assert (user_id, novel_id) not in tick_runtime._runtimes
    assert user_id not in tick_runtime._active_by_user

    # rmtree 必须成功 — 这是 fix 的真正卖点 (Windows file lock 释放).
    # ignore_errors=False 让我们能看到 PermissionError 而非静默掩盖。
    shutil.rmtree(data_dir, ignore_errors=False)
    assert not os.path.exists(data_dir)


def test_reload_cache_handles_active_user_correctly(tenant_root) -> None:
    """reload_cache 在 active 路径下应该重建 (供下次 get_runtime 直接拿到新 state),
    保证盘上数据被正确加载。"""
    user_id = "active_user"
    entry = novel_manager.create_novel(user_id, title="active 小说")
    novel_id = entry["id"]
    data_dir = novel_manager.get_novel_data_dir(user_id, novel_id)

    tick_runtime.get_runtime(user_id, novel_id)  # 触发 _active_by_user 注册
    assert tick_runtime._active_by_user.get(user_id) == novel_id

    # 外部写盘
    fresh_ts = TickState(data_dir=data_dir)
    fresh_ts.set_world_state(WorldState(era="reloaded"))
    fresh_ts.save()

    tick_runtime.reload_cache(user_id, novel_id)

    # active 路径下应该重建并保持指针
    assert (user_id, novel_id) in tick_runtime._runtimes
    assert tick_runtime._active_by_user.get(user_id) == novel_id
    # 重建后的 runtime 已载入新 state
    rt_after = tick_runtime._runtimes[(user_id, novel_id)]
    assert rt_after.tick_state.world_state.era == "reloaded"


def test_drop_runtime_alias_still_works(tenant_root) -> None:
    """向后兼容: drop_runtime 别名应当转发到 reload_cache (active 重建)。"""
    user_id = "compat_user"
    entry = novel_manager.create_novel(user_id, title="兼容测试")
    novel_id = entry["id"]
    tick_runtime.get_runtime(user_id, novel_id)

    # drop_runtime 别名应等价于 reload_cache
    tick_runtime.drop_runtime(user_id, novel_id)

    # active 路径下重建 — runtime 仍存在
    assert (user_id, novel_id) in tick_runtime._runtimes
