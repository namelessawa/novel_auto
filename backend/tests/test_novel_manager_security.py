"""novel_manager 输入校验与 path 边界测试 (v2.26 multi-tenant 更新).

覆盖:
1. ``_validate_novel_id`` 拒绝 path traversal / 特殊字符 / 超长。
2. 合法 ID (含中文 / 下划线 / 横线 / 字母数字) 应通过。
3. ``delete_novel`` 即便 manifest 里存在恶意 id, realpath 检查也会拦截。
"""

from __future__ import annotations

import tempfile

import pytest

import novel_manager
from novel_manager import (
    _assert_path_within,
    _validate_novel_id,
)


@pytest.fixture
def isolated_data_root(monkeypatch):
    """v2.26 — _DATA_ROOT / _USERS_ROOT 指向 tmp."""
    import os
    td = tempfile.mkdtemp()
    monkeypatch.setattr(novel_manager, "_DATA_ROOT", td)
    monkeypatch.setattr(novel_manager, "_USERS_ROOT", os.path.join(td, "users"))
    monkeypatch.setattr(
        novel_manager, "_LEGACY_NOVELS_DIR", os.path.join(td, "novels")
    )
    yield td


@pytest.mark.parametrize(
    "bad_id",
    [
        "../etc",
        "..",
        "../../tmp",
        "foo/bar",
        "foo\\bar",
        "foo bar",  # 空格
        "foo:bar",  # 冒号 (Windows 盘符标记)
        "",  # 空串
        "a" * 65,  # 超长
        "foo?",
        "foo*",
        "foo;rm -rf",
    ],
)
def test_validate_rejects_malformed(bad_id: str) -> None:
    with pytest.raises(ValueError):
        _validate_novel_id(bad_id)


@pytest.mark.parametrize(
    "good_id",
    [
        "default",
        "test_story_A",
        "未命名小说_573b4c",
        "默认小说_55f37f",
        "abc-123",
        "a",
        "x" * 64,  # 上限
    ],
)
def test_validate_accepts_normal(good_id: str) -> None:
    assert _validate_novel_id(good_id) == good_id


def test_assert_path_within_root_rejects_escape(tmp_path) -> None:
    """v2.26 — _assert_path_within 通用 sanitizer 验证 commonpath 模式."""
    fake_root = tmp_path / "novels"
    fake_root.mkdir()

    # 同目录内合法
    _assert_path_within(str(fake_root / "story_a"), str(fake_root))

    # 越界路径必须抛
    outside = tmp_path / "evil"
    with pytest.raises(ValueError):
        _assert_path_within(str(outside), str(fake_root))


def test_delete_novel_rejects_invalid_id(isolated_data_root) -> None:
    """delete_novel 必须先 _validate_novel_id, 不让 ../etc 落到 shutil.rmtree。"""
    with pytest.raises(ValueError):
        novel_manager.delete_novel("alice", "../etc/passwd")


def test_get_novel_data_dir_rejects_invalid_id(isolated_data_root) -> None:
    with pytest.raises(ValueError):
        novel_manager.get_novel_data_dir("alice", "../../tmp")


def test_update_title_rejects_invalid_id(isolated_data_root) -> None:
    with pytest.raises(ValueError):
        novel_manager.update_title("alice", "foo/bar", "新标题")


def test_get_novel_rejects_invalid_id(isolated_data_root) -> None:
    with pytest.raises(ValueError):
        novel_manager.get_novel("alice", "..")
