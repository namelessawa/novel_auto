"""TickState / SummaryTree 损坏文件 quarantine (v2.21)。

回归 P1:此前 load 失败只 log + return False, 下一次 save() 用 fresh 状态
原子覆盖原路径, 真实数据永久丢失。新行为:文件被 rename 到
``{path}.corrupt.{ts}``, 下次 save 写干净文件, 旧文件人工可恢复。
"""

from __future__ import annotations

import glob
import json
import os

import pytest

from memory.summary_tree import SummaryTree
from memory.tick_state import STATE_FILENAME, TickState


def _list_corrupt(path_base: str) -> list[str]:
    return sorted(glob.glob(f"{path_base}.corrupt.*"))


# ---------------------------------------------------------------------------
# TickState
# ---------------------------------------------------------------------------


def test_tick_state_json_corruption_quarantines(tmp_path) -> None:
    state_path = tmp_path / STATE_FILENAME
    state_path.write_text("not valid json {[", encoding="utf-8")

    ts = TickState(data_dir=str(tmp_path))
    assert ts.load() is False

    # 原路径已被移走
    assert not state_path.exists()
    # 隔离文件存在
    corrupted = _list_corrupt(str(state_path))
    assert len(corrupted) == 1, f"expected 1 quarantine file, got {corrupted}"
    with open(corrupted[0], "r", encoding="utf-8") as f:
        assert "not valid json" in f.read()


def test_tick_state_validation_failure_quarantines(tmp_path) -> None:
    """payload 是合法 JSON 但 Pydantic 校验失败 — 同样 quarantine。"""
    state_path = tmp_path / STATE_FILENAME
    # current_tick 写成不可 int 的字符串 → ValidationError
    state_path.write_text(
        json.dumps({"current_tick": "not_a_number", "world_state": {}}),
        encoding="utf-8",
    )

    ts = TickState(data_dir=str(tmp_path))
    assert ts.load() is False

    corrupted = _list_corrupt(str(state_path))
    assert len(corrupted) == 1


def test_tick_state_save_after_quarantine_does_not_overwrite_original(tmp_path) -> None:
    """quarantine 后 save() 写新文件; 旧 corrupt.* 文件保持原内容不被覆盖。"""
    state_path = tmp_path / STATE_FILENAME
    state_path.write_text("CORRUPTED_PAYLOAD_PROBE", encoding="utf-8")

    ts = TickState(data_dir=str(tmp_path))
    ts.load()  # quarantines

    ts.save()  # 写新干净文件
    assert state_path.exists()
    # 新文件不再是 corrupted probe
    assert "CORRUPTED_PAYLOAD_PROBE" not in state_path.read_text(encoding="utf-8")

    # 隔离档案依然保留原始 probe
    corrupted = _list_corrupt(str(state_path))
    assert len(corrupted) == 1
    assert "CORRUPTED_PAYLOAD_PROBE" in open(corrupted[0], "r", encoding="utf-8").read()


def test_tick_state_missing_file_no_quarantine(tmp_path) -> None:
    """文件不存在 — 不应创建 corrupt.* 假阳性。"""
    ts = TickState(data_dir=str(tmp_path))
    assert ts.load() is False
    state_path = tmp_path / STATE_FILENAME
    corrupted = _list_corrupt(str(state_path))
    assert corrupted == []


# ---------------------------------------------------------------------------
# SummaryTree
# ---------------------------------------------------------------------------


def test_summary_tree_json_corruption_quarantines(tmp_path) -> None:
    path = tmp_path / "summary_tree.json"
    path.write_text("}{ broken", encoding="utf-8")

    tree = SummaryTree()
    assert tree.load_from_disk(str(path)) is False

    assert not path.exists()
    corrupted = _list_corrupt(str(path))
    assert len(corrupted) == 1


def test_summary_tree_validation_failure_quarantines(tmp_path) -> None:
    """合法 JSON 但缺 root 关键字段 → KeyError → quarantine。"""
    path = tmp_path / "summary_tree.json"
    path.write_text(json.dumps({"leaves": []}), encoding="utf-8")  # 没有 root

    tree = SummaryTree()
    assert tree.load_from_disk(str(path)) is False

    corrupted = _list_corrupt(str(path))
    assert len(corrupted) == 1
