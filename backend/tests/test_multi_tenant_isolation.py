"""v2.26 — novel_manager + tick_runtime user_id 命名空间隔离。"""

from __future__ import annotations

import os
import tempfile

import pytest

import novel_manager


@pytest.fixture
def isolated_data_root(monkeypatch):
    td = tempfile.mkdtemp()
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", td)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", os.path.join(td, "users"))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", os.path.join(td, "novels")
    )
    yield td


def test_create_novel_under_user_namespace(isolated_data_root):
    entry = novel_manager.create_novel("user_alice", "Alice 的小说")
    assert entry["id"]
    assert entry["title"] == "Alice 的小说"
    # 路径应在 users/user_alice/novels/ 下
    path = novel_manager.get_novel_data_dir("user_alice", entry["id"])
    assert "user_alice" in path
    assert os.path.isdir(path)


def test_users_cannot_see_each_others_novels(isolated_data_root):
    novel_manager.create_novel("alice", "A1")
    novel_manager.create_novel("alice", "A2")
    novel_manager.create_novel("bob", "B1")

    alice_list = novel_manager.list_novels("alice")
    bob_list = novel_manager.list_novels("bob")

    assert len(alice_list) == 2
    assert len(bob_list) == 1
    assert {n["title"] for n in alice_list} == {"A1", "A2"}
    assert {n["title"] for n in bob_list} == {"B1"}


def test_get_novel_isolated_by_user(isolated_data_root):
    a = novel_manager.create_novel("alice", "A1")
    # bob 不能取到 alice 的 novel
    assert novel_manager.get_novel("bob", a["id"]) is None
    # alice 能
    assert novel_manager.get_novel("alice", a["id"]) is not None


def test_delete_isolated_by_user(isolated_data_root):
    a = novel_manager.create_novel("alice", "A1")
    # bob 删 alice 的 novel 返回 False (manifest 没记录)
    assert novel_manager.delete_novel("bob", a["id"]) is False
    # 文件应仍存在
    assert os.path.isdir(novel_manager.get_novel_data_dir("alice", a["id"]))
    # alice 自己删 OK
    assert novel_manager.delete_novel("alice", a["id"]) is True


def test_update_title_isolated(isolated_data_root):
    a = novel_manager.create_novel("alice", "A1")
    # bob 改 alice 的 → None
    assert novel_manager.update_title("bob", a["id"], "hacked") is None
    # 文件未改
    novel = novel_manager.get_novel("alice", a["id"])
    assert novel["title"] == "A1"


def test_invalid_user_id_rejected(isolated_data_root):
    with pytest.raises(ValueError, match="invalid user_id"):
        novel_manager.get_novel_data_dir("../etc/passwd", "n1")
    with pytest.raises(ValueError):
        novel_manager.get_novel_data_dir("user/with/slash", "n1")
    with pytest.raises(ValueError):
        novel_manager.get_novel_data_dir("", "n1")


def test_invalid_novel_id_rejected(isolated_data_root):
    novel_manager.create_novel("alice", "A1")
    with pytest.raises(ValueError, match="invalid novel_id"):
        novel_manager.get_novel_data_dir("alice", "../../etc")


def test_touch_last_accessed_updates_timestamp(isolated_data_root):
    a = novel_manager.create_novel("alice", "A1")
    old_ts = a["last_accessed_at"]
    import time
    time.sleep(0.01)
    novel_manager.touch_last_accessed("alice", a["id"])
    refreshed = novel_manager.get_novel("alice", a["id"])
    assert refreshed["last_accessed_at"] >= old_ts


def test_list_all_users_with_novels(isolated_data_root):
    novel_manager.create_novel("alice", "A1")
    novel_manager.create_novel("bob", "B1")
    novel_manager.create_novel("carol", "C1")
    users = set(novel_manager.list_all_users_with_novels())
    assert {"alice", "bob", "carol"} <= users
