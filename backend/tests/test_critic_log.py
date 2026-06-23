"""Phase 6-C iter#5 — critic decision JSONL log persistence.

orchestrator 每 tick 把 narrator_out.critique_trace 的 lightweight 字段
append 到 `{data_dir}/critic_log.jsonl`. 本 test 锁住:

* empty critique_trace → no-op (jsonl 不创建)
* 非空 trace → 1 行, schema 字段齐
* 同 data_dir 多 tick → append (而非覆盖)
* surviving_triggers code 排序去重
* invalid trigger entries 跳过 (isinstance + key check)
"""

from __future__ import annotations

import json
import os

import pytest

from agents.narrator_agent import NarratorOutput
from agents.orchestrator import _append_critic_log


def _output(
    *,
    critique_trace: dict | None = None,
    critique_action: str = "ACCEPT",
    new_opening_signature: str = "他走进",
) -> NarratorOutput:
    return NarratorOutput(
        should_narrate=True,
        narrative_text="一段叙述",
        critique_trace=critique_trace or {},
        critique_action=critique_action,
        new_opening_signature=new_opening_signature,
    )


def test_empty_trace_no_jsonl_created(tmp_path) -> None:
    """critique_trace=空 → jsonl 文件不创建, 无 IO."""
    out = _output(critique_trace={})
    _append_critic_log(str(tmp_path), tick=1, narrator_out=out)
    assert not (tmp_path / "critic_log.jsonl").exists()


def test_non_empty_trace_writes_row(tmp_path) -> None:
    """trace 非空 → 1 行 JSONL, 含全部 schema 字段."""
    trace = {
        "surviving_triggers": [
            {"code": "A1", "severity": "medium", "evidence": "实词重复"},
            {"code": "D2", "severity": "medium", "evidence": "形容词堆砌"},
        ],
        "decision_trail": ["round 1: det=2 medium=2 → POLISH"],
    }
    out = _output(critique_trace=trace, critique_action="ACCEPT",
                  new_opening_signature="他走进")
    _append_critic_log(str(tmp_path), tick=5, narrator_out=out)

    log = tmp_path / "critic_log.jsonl"
    assert log.is_file()
    lines = log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row == {
        "tick": 5,
        "action": "ACCEPT",
        "surviving_codes": ["A1", "D2"],
        "decision_trail": ["round 1: det=2 medium=2 → POLISH"],
        "new_opening_signature": "他走进",
    }


def test_multi_tick_appends_not_overwrites(tmp_path) -> None:
    """同 data_dir 多 tick → 多行 append, 顺序保留."""
    for tick in (1, 2, 3):
        out = _output(
            critique_trace={"surviving_triggers": [], "decision_trail": [f"tick {tick}"]},
            critique_action="ACCEPT",
        )
        _append_critic_log(str(tmp_path), tick=tick, narrator_out=out)

    log = tmp_path / "critic_log.jsonl"
    lines = log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    ticks = [json.loads(line)["tick"] for line in lines]
    assert ticks == [1, 2, 3]


def test_surviving_codes_sorted_and_deduped(tmp_path) -> None:
    """同 code 重复触发 → sorted + dedupe."""
    trace = {
        "surviving_triggers": [
            {"code": "D2"},
            {"code": "A1"},
            {"code": "A1"},
            {"code": "B4"},
        ],
        "decision_trail": [],
    }
    out = _output(critique_trace=trace)
    _append_critic_log(str(tmp_path), tick=1, narrator_out=out)
    row = json.loads((tmp_path / "critic_log.jsonl").read_text(encoding="utf-8").strip())
    assert row["surviving_codes"] == ["A1", "B4", "D2"]


def test_invalid_trigger_entries_skipped(tmp_path) -> None:
    """非 dict / 缺 code 的 trigger 跳过, 不抛."""
    trace = {
        "surviving_triggers": [
            {"code": "A1"},
            "not-a-dict",  # str
            {"severity": "medium"},  # 无 code
            None,  # NoneType
            {"code": "B4"},
        ],
        "decision_trail": [],
    }
    out = _output(critique_trace=trace)
    _append_critic_log(str(tmp_path), tick=1, narrator_out=out)
    row = json.loads((tmp_path / "critic_log.jsonl").read_text(encoding="utf-8").strip())
    assert row["surviving_codes"] == ["A1", "B4"]


def test_unicode_evidence_safe_jsonl(tmp_path) -> None:
    """中文 evidence + ensure_ascii=False 不破 jsonl decode."""
    trace = {
        "surviving_triggers": [{"code": "A4", "evidence": "仿佛×3 出现在: '...仿佛听到...'"}],
        "decision_trail": ["round 1: 仿佛 触发 → REWRITE"],
    }
    out = _output(critique_trace=trace, critique_action="REWRITE")
    _append_critic_log(str(tmp_path), tick=1, narrator_out=out)
    row = json.loads((tmp_path / "critic_log.jsonl").read_text(encoding="utf-8").strip())
    assert row["action"] == "REWRITE"
    assert "仿佛" in row["decision_trail"][0]
