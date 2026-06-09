"""Regression: drop_runtime 不得用 stale in-memory state 覆盖盘上数据。

Bug 复盘 (2026-06-09)
---------------------
bootstrap_world 跑完后, ``_reload_runtime`` 调 ``drop_runtime``, 旧实现里
``rt.close()`` 会把 cached runtime 的 in-memory TickState 原子写回盘
(``self.tick_state.save``) — 而该 in-memory 状态是 bootstrap **之前**
frontend 触发 ``set_active_novel`` 时构造的, 内容是空的。结果: bootstrap
刚写盘的 5 角色 / 5 地点 / 5 伏笔 / 4 风格锚点全被空覆盖, Narrator 跑
30 个 tick 后 tick_state.json 里只剩 ``era=初始纪元`` 和泛化的
``loc_wilderness``, 跟标题完全脱节。

Fix: ``drop_runtime`` 改为纯丢弃缓存语义, 只 ``tick_db.close()``
释放 SQLite 文件锁, 不再 save 任何状态。
"""

from __future__ import annotations

import json
import os

import pytest

import novel_manager
import tick_runtime
from memory.tick_state import TickState
from memory_system.models import CharacterProfile, WorldState


@pytest.fixture
def tenant_root(tmp_path, monkeypatch):
    """把 novel_manager 的数据根重指向 tmp_path, 测试结束自动清理。"""
    data_root = tmp_path / "data"
    users_root = data_root / "users"
    users_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", str(data_root))
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", str(users_root))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", str(data_root / "novels")
    )
    tick_runtime._clear_for_tests()
    yield
    # 释放 SQLite 句柄, 防 Windows tmp 清理报错
    for rt in list(tick_runtime._runtimes.values()):
        try:
            rt.tick_db.close()
        except Exception:
            pass
    tick_runtime._clear_for_tests()


def _read_disk_state(data_dir: str) -> dict:
    with open(os.path.join(data_dir, "tick_state.json"), encoding="utf-8") as f:
        return json.load(f)


def test_drop_runtime_preserves_externally_written_disk(tenant_root) -> None:
    """模拟 bootstrap 直写盘 → drop_runtime → 盘上数据必须留下。"""
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
    fresh_ts.upsert_character_profile(
        CharacterProfile(
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
    )
    fresh_ts.save()

    # 盘上数据现是新鲜的 bootstrap 内容
    on_disk_before = _read_disk_state(data_dir)
    assert on_disk_before["world_state"]["era"] == "近未来魔法衰退纪元"
    assert "char_aria" in on_disk_before["character_profiles"]

    # 3. bootstrap_routes._reload_runtime 调 drop_runtime —
    #    旧实现会 rt.close() → rt.tick_state.save() 把 stale 空状态写回盘。
    tick_runtime.drop_runtime(user_id, novel_id)

    # 4. 盘上数据必须仍是 bootstrap 内容, 不能被空覆盖。
    on_disk_after = _read_disk_state(data_dir)
    assert on_disk_after["world_state"]["era"] == "近未来魔法衰退纪元", (
        "bootstrap era 被 stale in-memory state 覆盖了: "
        f"{on_disk_after['world_state']!r}"
    )
    assert "char_aria" in on_disk_after["character_profiles"], (
        "bootstrap 角色丢失: "
        f"{list(on_disk_after['character_profiles'].keys())!r}"
    )

    # 5. drop 后重新 get → 新 runtime 必须从盘载入 bootstrap 数据。
    rt_after = tick_runtime.get_runtime(user_id, novel_id)
    assert rt_after is not rt
    assert rt_after.tick_state.world_state.era == "近未来魔法衰退纪元"
    assert rt_after.tick_state.get_character_profile("char_aria") is not None
