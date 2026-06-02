"""Tests for BranchManager — fork / archive / tree / 持久化。"""

from __future__ import annotations

import os

import pytest

from narrative.branch_manager import BranchManager


@pytest.fixture
def setup_root(tmp_path):
    """准备一个看起来像 novel data_dir 的目录。"""
    root = tmp_path / "novel"
    root.mkdir()
    # 模拟一些 novel 文件
    (root / "tick_state.json").write_text("{}", encoding="utf-8")
    (root / "narratives").mkdir()
    (root / "narratives" / "tick_000001.txt").write_text("第一段", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# 基础
# ---------------------------------------------------------------------------


def test_init_creates_canonical_main(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    assert bm.canonical_branch_id == "main"
    assert bm.get("main") is not None
    assert bm.data_dir_for("main") == str(setup_root)


def test_list_branches_only_active_by_default(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    assert len(bm.list_branches()) == 1  # main


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


def test_fork_copies_data_dir(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    meta = bm.fork(
        from_branch_id="main",
        new_branch_id="branch_a",
        forked_at_tick=50,
        choice_description="alice 的选择",
        choice_options=["回家", "追查"],
        selected_option="回家",
    )
    new_dir = bm.data_dir_for("branch_a")
    assert os.path.isdir(new_dir)
    assert os.path.exists(os.path.join(new_dir, "tick_state.json"))
    assert os.path.exists(
        os.path.join(new_dir, "narratives", "tick_000001.txt")
    )
    assert meta.parent_branch_id == "main"
    assert meta.forked_at_tick == 50


def test_fork_rejects_duplicate_id(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    bm.fork(
        from_branch_id="main",
        new_branch_id="branch_a",
        forked_at_tick=10,
        choice_description="x",
    )
    with pytest.raises(ValueError):
        bm.fork(
            from_branch_id="main",
            new_branch_id="branch_a",
            forked_at_tick=10,
            choice_description="x",
        )


def test_fork_rejects_missing_parent(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    with pytest.raises(ValueError):
        bm.fork(
            from_branch_id="ghost",
            new_branch_id="branch_a",
            forked_at_tick=10,
            choice_description="x",
        )


def test_fork_skips_branches_subdir(setup_root) -> None:
    """fork 时不要把 branches/ 子目录递归拷贝 (会导致无穷递归)。"""
    bm = BranchManager(str(setup_root))
    bm.fork(
        from_branch_id="main",
        new_branch_id="branch_a",
        forked_at_tick=10,
        choice_description="x",
    )
    # 现在 main 下有 branches/branch_a/, 再 fork main 一次, 不应把
    # branch_a 拷贝进 branch_b
    bm.fork(
        from_branch_id="main",
        new_branch_id="branch_b",
        forked_at_tick=20,
        choice_description="y",
    )
    branch_b_dir = bm.data_dir_for("branch_b")
    assert not os.path.exists(os.path.join(branch_b_dir, "branches"))


# ---------------------------------------------------------------------------
# Archive / canonical / annotate
# ---------------------------------------------------------------------------


def test_archive_and_unarchive(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    bm.fork(
        from_branch_id="main",
        new_branch_id="branch_a",
        forked_at_tick=10,
        choice_description="x",
    )
    assert bm.archive("branch_a") is True
    assert bm.get("branch_a").archived is True
    assert "branch_a" not in {m.branch_id for m in bm.list_branches()}
    assert "branch_a" in {
        m.branch_id for m in bm.list_branches(include_archived=True)
    }
    assert bm.unarchive("branch_a") is True
    assert "branch_a" in {m.branch_id for m in bm.list_branches()}


def test_archive_canonical_raises(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    with pytest.raises(ValueError):
        bm.archive("main")


def test_set_canonical_switches_default_data_dir(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    bm.fork(
        from_branch_id="main",
        new_branch_id="branch_a",
        forked_at_tick=10,
        choice_description="x",
    )
    bm.set_canonical("branch_a")
    assert bm.canonical_branch_id == "branch_a"
    # data_dir_for 对 canonical 返回 root, 而 branch_a 现在是 canonical
    assert bm.data_dir_for("branch_a") == str(setup_root)


def test_annotate(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    bm.fork(
        from_branch_id="main",
        new_branch_id="branch_a",
        forked_at_tick=10,
        choice_description="x",
    )
    assert bm.annotate("branch_a", "实验性走向") is True
    assert bm.get("branch_a").notes == "实验性走向"


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------


def test_build_tree(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    bm.fork(
        from_branch_id="main",
        new_branch_id="b1",
        forked_at_tick=10,
        choice_description="x",
    )
    bm.fork(
        from_branch_id="b1",
        new_branch_id="b2",
        forked_at_tick=20,
        choice_description="y",
    )
    tree = bm.build_tree()
    assert tree is not None
    assert tree.meta.branch_id == "main"
    assert len(tree.children) == 1
    assert tree.children[0].meta.branch_id == "b1"
    assert tree.children[0].children[0].meta.branch_id == "b2"


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def test_save_load_roundtrip(setup_root) -> None:
    bm = BranchManager(str(setup_root))
    bm.fork(
        from_branch_id="main",
        new_branch_id="branch_a",
        forked_at_tick=15,
        choice_description="alice 的选择",
        choice_options=["回家", "追查"],
        selected_option="追查",
    )
    bm.annotate("branch_a", "对照分支")

    fresh = BranchManager(str(setup_root))
    assert fresh.load() is True
    meta = fresh.get("branch_a")
    assert meta is not None
    assert meta.forked_at_tick == 15
    assert meta.selected_option == "追查"
    assert meta.notes == "对照分支"


def test_load_missing_returns_false(tmp_path) -> None:
    bm = BranchManager(str(tmp_path / "empty"))
    assert bm.load() is False
