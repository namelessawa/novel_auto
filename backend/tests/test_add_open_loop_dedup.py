"""iter#108 — add_open_loop dedup gate.

iter#106 review MEDIUM gap: 若 Showrunner 在 tick T 关 loop_X, EventInjector
在同 tick 重新 open ID=loop_X 的新 loop, 既往会静默覆盖, 调用方无知. 加
logger.warning 让 bug 可见, 行为保持向后兼容 (overwrite-with-warn).
"""

from __future__ import annotations

import logging

import pytest

from memory.tick_state import TickState
from memory_system.models import OpenLoop, TickLocation, WorldState


def _make_loop(id_: str, desc: str = "原始", urgency: int = 5) -> OpenLoop:
    return OpenLoop(
        id=id_,
        opened_tick=0,
        description=desc,
        urgency=urgency,
        type="mystery",
        last_referenced_tick=0,
    )


def test_add_open_loop_first_time_silent(tmp_path, caplog):
    """首次添加 — 无 warning."""
    caplog.set_level(logging.WARNING, logger="memory.tick_state")
    ts = TickState(data_dir=str(tmp_path))
    ts.add_open_loop(_make_loop("loop_a"))
    assert len(ts.get_open_loops()) == 1
    assert "duplicate" not in caplog.text


def test_add_open_loop_duplicate_logs_warning(tmp_path, caplog):
    """同 ID 重复添加 — 必须 logger.warning, 且行为是 overwrite."""
    caplog.set_level(logging.WARNING, logger="memory.tick_state")
    ts = TickState(data_dir=str(tmp_path))
    ts.add_open_loop(_make_loop("loop_a", desc="原始"))
    ts.add_open_loop(_make_loop("loop_a", desc="覆盖", urgency=8))

    # 行为: 新值覆盖
    loops = ts.get_open_loops()
    assert len(loops) == 1
    assert loops[0].description == "覆盖"
    assert loops[0].urgency == 8

    # 警告: 必须含 'duplicate' + ID
    assert "duplicate" in caplog.text
    assert "loop_a" in caplog.text


def test_add_open_loop_close_then_reopen_no_warning(tmp_path, caplog):
    """close → reopen 同 ID — 已 pop 出池, 再加视作首次, 不警告."""
    caplog.set_level(logging.WARNING, logger="memory.tick_state")
    ts = TickState(data_dir=str(tmp_path))
    ts.add_open_loop(_make_loop("loop_a", desc="原始"))
    ts.close_open_loop("loop_a")
    assert len(ts.get_open_loops()) == 0

    ts.add_open_loop(_make_loop("loop_a", desc="重生"))
    loops = ts.get_open_loops()
    assert len(loops) == 1
    assert loops[0].description == "重生"
    # 这次不该有 warning (上一次已被 close 出池)
    assert "duplicate" not in caplog.text


def test_add_open_loop_three_dup_logs_two_warnings(tmp_path, caplog):
    """3 次重复 → 2 次 warning."""
    caplog.set_level(logging.WARNING, logger="memory.tick_state")
    ts = TickState(data_dir=str(tmp_path))
    ts.add_open_loop(_make_loop("loop_x"))
    ts.add_open_loop(_make_loop("loop_x"))
    ts.add_open_loop(_make_loop("loop_x"))
    assert caplog.text.count("duplicate") == 2
