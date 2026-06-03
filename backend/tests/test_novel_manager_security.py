"""novel_manager 输入校验与 path 边界测试 (v2.15)。

覆盖:
1. ``_validate_novel_id`` 拒绝 path traversal / 特殊字符 / 超长。
2. 合法 ID (含中文 / 下划线 / 横线 / 字母数字) 应通过。
3. ``delete_novel`` 即便 manifest 里存在恶意 id, realpath 检查也会拦截。
"""

from __future__ import annotations

import os

import pytest

import novel_manager
from novel_manager import (
    _assert_path_within_novels_root,
    _validate_novel_id,
)


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


def test_assert_path_within_root_rejects_escape(tmp_path, monkeypatch) -> None:
    """模拟 novels 根在 tmp_path 下, 越界路径必须被拒绝。"""
    fake_root = tmp_path / "novels"
    fake_root.mkdir()
    monkeypatch.setattr(novel_manager, "_NOVELS_DIR", str(fake_root))

    # 同目录内合法
    novel_manager._assert_path_within_novels_root(str(fake_root / "story_a"))

    # 越界路径必须抛
    outside = tmp_path / "evil"
    with pytest.raises(ValueError):
        novel_manager._assert_path_within_novels_root(str(outside))


def test_delete_novel_rejects_invalid_id() -> None:
    """delete_novel 必须先 _validate_novel_id, 不让 ../etc 落到 shutil.rmtree。"""
    with pytest.raises(ValueError):
        novel_manager.delete_novel("../etc/passwd")


def test_get_novel_data_dir_rejects_invalid_id() -> None:
    with pytest.raises(ValueError):
        novel_manager.get_novel_data_dir("../../tmp")


def test_update_title_rejects_invalid_id() -> None:
    with pytest.raises(ValueError):
        novel_manager.update_title("foo/bar", "新标题")


def test_get_novel_rejects_invalid_id() -> None:
    with pytest.raises(ValueError):
        novel_manager.get_novel("..")
