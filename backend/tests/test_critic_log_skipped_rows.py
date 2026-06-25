"""Phase 6 iter#R — critic_log.jsonl 加 skipped 行.

现 _append_critic_log 只在 critique_trace 非空 (= critic 真跑了) 时写一行,
analyzer 没法区分 "critic 没跑" (length-gate / importance-gate / disabled) vs
"critic 跑了但 ACCEPT". 加 skipped 行让两种情况都可追踪.

锁定:
* critique_trace 非空 → 写 ACCEPT/REVISE/REWRITE 行 (老行为)
* critique_trace 空 + critique_skip_reason 设了 → 写 SKIP 行
* critique_trace 空 + skip_reason 空 → 不写 (silent tick, narrator 都没跑)
* SKIP 行的 schema 含 tick / action="SKIP" / skip_reason / surviving_codes=[]
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
for p in (_ROOT, _BACKEND):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import pytest

from agents.orchestrator import _append_critic_log
from agents.narrator_agent import NarratorOutput


def _read_log(data_dir: str) -> list[dict]:
    path = os.path.join(data_dir, "critic_log.jsonl")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Old behavior preserved
# ---------------------------------------------------------------------------


def test_critique_trace_present_writes_decision_row(tmp_path) -> None:
    """critique_trace 非空 → 写 ACCEPT 行 (老行为不破)."""
    data_dir = str(tmp_path)
    out = NarratorOutput(
        should_narrate=True,
        narrative_text="一段叙述",
        critique_trace={
            "surviving_triggers": [{"code": "A1", "severity": "medium"}],
            "decision_trail": ["critique:initial"],
        },
        critique_action="ACCEPT",
    )
    _append_critic_log(data_dir, tick=5, narrator_out=out)
    rows = _read_log(data_dir)
    assert len(rows) == 1
    assert rows[0]["tick"] == 5
    assert rows[0]["action"] == "ACCEPT"
    assert rows[0]["surviving_codes"] == ["A1"]


# ---------------------------------------------------------------------------
# iter#R: SKIP row when critic was gated
# ---------------------------------------------------------------------------


def test_empty_trace_with_skip_reason_writes_skip_row(tmp_path) -> None:
    """critique_trace 空 + critique_skip_reason 设了 → 写 SKIP 行."""
    data_dir = str(tmp_path)
    out = NarratorOutput(
        should_narrate=True,
        narrative_text="短段落 (低于 600 字 length gate)",
        critique_trace={},
        critique_action="",
        critique_skip_reason="length_gate",
    )
    _append_critic_log(data_dir, tick=7, narrator_out=out)
    rows = _read_log(data_dir)
    assert len(rows) == 1
    assert rows[0]["tick"] == 7
    assert rows[0]["action"] == "SKIP"
    assert rows[0]["skip_reason"] == "length_gate"
    assert rows[0]["surviving_codes"] == []


def test_empty_trace_no_skip_reason_silent(tmp_path) -> None:
    """critique_trace 空 + skip_reason 空 → 不写 (silent tick / narrator 也没跑)."""
    data_dir = str(tmp_path)
    out = NarratorOutput(
        should_narrate=False,
        critique_trace={},
        critique_action="",
        critique_skip_reason="",
    )
    _append_critic_log(data_dir, tick=8, narrator_out=out)
    rows = _read_log(data_dir)
    assert rows == []


def test_skip_reason_importance_gate(tmp_path) -> None:
    """importance_gate skip reason 也走 SKIP 行."""
    data_dir = str(tmp_path)
    out = NarratorOutput(
        should_narrate=True,
        narrative_text="一段叙述",
        critique_skip_reason="importance_gate",
    )
    _append_critic_log(data_dir, tick=9, narrator_out=out)
    rows = _read_log(data_dir)
    assert rows[0]["action"] == "SKIP"
    assert rows[0]["skip_reason"] == "importance_gate"


def test_skip_reason_critic_disabled(tmp_path) -> None:
    data_dir = str(tmp_path)
    out = NarratorOutput(
        should_narrate=True,
        narrative_text="一段叙述",
        critique_skip_reason="critic_disabled",
    )
    _append_critic_log(data_dir, tick=10, narrator_out=out)
    rows = _read_log(data_dir)
    assert rows[0]["action"] == "SKIP"
    assert rows[0]["skip_reason"] == "critic_disabled"


# ---------------------------------------------------------------------------
# Multi-tick: mixed SKIP and ACCEPT rows
# ---------------------------------------------------------------------------


def test_multi_tick_mixed_rows(tmp_path) -> None:
    data_dir = str(tmp_path)
    out_accept = NarratorOutput(
        should_narrate=True,
        narrative_text="x",
        critique_trace={"surviving_triggers": [], "decision_trail": []},
        critique_action="ACCEPT",
    )
    out_skip = NarratorOutput(
        should_narrate=True,
        narrative_text="x",
        critique_skip_reason="length_gate",
    )
    _append_critic_log(data_dir, 1, out_accept)
    _append_critic_log(data_dir, 2, out_skip)
    _append_critic_log(data_dir, 3, out_accept)

    rows = _read_log(data_dir)
    assert [r["tick"] for r in rows] == [1, 2, 3]
    assert [r["action"] for r in rows] == ["ACCEPT", "SKIP", "ACCEPT"]
