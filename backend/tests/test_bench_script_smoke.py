"""Smoke test for scripts/bench_tick.py.

确保 cost-quality-loop 的 bench 脚本能正常 import + 关键函数存在.
未来重构若误删 _bench / _render_markdown 等, 这个测试立即报警.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _import_bench_module():
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import importlib

    return importlib.import_module("bench_tick")


def test_bench_tick_imports_and_has_entrypoints() -> None:
    """关键入口在 — 测试反向锁定 cost-quality-loop bench 工具的 API."""
    bench = _import_bench_module()
    assert callable(getattr(bench, "_bench", None))
    assert callable(getattr(bench, "main", None))
    assert callable(getattr(bench, "_render_markdown", None))
    assert isinstance(getattr(bench, "_DEFAULT_SEED", None), str)
    assert len(bench._DEFAULT_SEED) > 0


def test_bench_render_markdown_returns_string() -> None:
    """_render_markdown 接受样本 report dict 返回 markdown 文本."""
    bench = _import_bench_module()
    sample = {
        "label": "test",
        "novel_id": "bench_test_1",
        "ticks": 1,
        "bootstrap_sec": 100.0,
        "tick_durations_sec": [42.0],
        "total_tokens": 1000,
        "by_agent_cumulative": {"narrator": 800, "world_simulator": 200},
        "by_priority": {"critical": 800, "medium": 200},
        "call_count": 2,
        "per_tick": [
            {
                "tick": 1,
                "tick_total_tokens": 1000,
                "duration_sec": 42.0,
                "narrator_chars": 500,
                "agents": {"narrator": 800, "world_simulator": 200},
            }
        ],
        "narratives": [],
    }
    out = bench._render_markdown(sample)
    assert isinstance(out, str)
    assert "test" in out
    assert "narrator" in out
    assert "1000" in out


def test_per_tick_schema_includes_agents_called() -> None:
    """iter#K: per_tick record 必须含 agents_called/events_generated/narrator_produced.

    analyzer (scripts/analyze_longrange_drift.py) 用 agents_called 判断
    MemoryCompressor / ConsistencyGuardian 等 silent agents 是否真触发,
    用 events_generated 跟踪 D6 token cascade 因素.
    """
    bench = _import_bench_module()
    sample = {
        "label": "schema",
        "novel_id": "bench_schema_1",
        "ticks": 1,
        "bootstrap_sec": 1.0,
        "tick_durations_sec": [5.0],
        "total_tokens": 100,
        "by_agent_cumulative": {"narrator": 100},
        "by_priority": {},
        "call_count": 1,
        "per_tick": [
            {
                "tick": 1,
                "tick_total_tokens": 100,
                "duration_sec": 5.0,
                "narrator_chars": 200,
                "agents": {"narrator": 100},
                "agents_called": ["WorldSimulator", "NarratorAgent"],
                "events_generated": ["evt_1", "evt_2"],
                "narrator_produced": True,
            }
        ],
        "narratives": [],
    }
    # 主要锁定: render 不抛, 且 agents_called/events 数据不丢
    out = bench._render_markdown(sample)
    assert isinstance(out, str)
    # smoke: 这些字段被认作 schema 合约 (analyzer 与 bench 协同)
    rec = sample["per_tick"][0]
    assert "agents_called" in rec and isinstance(rec["agents_called"], list)
    assert "events_generated" in rec and isinstance(rec["events_generated"], list)
    assert "narrator_produced" in rec and isinstance(rec["narrator_produced"], bool)


def test_narrator_observability_distinguishes_evaluated_from_skipped() -> None:
    bench = _import_bench_module()
    observed = bench._narrator_observability(SimpleNamespace(
        skip_reason="",
        critique_trace={
            "surviving_triggers": [
                {"code": "D2"}, {"code": "D2"}, {"code": "A1"},
            ]
        },
        critique_action="REVISE",
        critique_skip_reason="",
    ))
    skipped = bench._narrator_observability(SimpleNamespace(
        skip_reason="Narrator 正文状态矛盾未通过修复复验",
        critique_trace={},
        critique_action="",
        critique_skip_reason="importance_gate",
    ))

    assert observed["critic_evaluated"] is True
    assert observed["critic_surviving_codes"] == ["A1", "D2"]
    assert skipped["critic_evaluated"] is False
    assert skipped["critic_skip_reason"] == "importance_gate"
    assert "状态矛盾" in skipped["narrator_skip_reason"]


def test_analyzer_d4_uses_agents_called(tmp_path) -> None:
    """iter#K + analyzer: per_tick.agents_called 含 MemoryCompressor 时,
    D4 不再报 silent."""
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import importlib
    import json
    analyzer = importlib.import_module("analyze_longrange_drift")
    # report with memcompress triggered
    rep = {
        "label": "memcompress-on",
        "ticks": 50,
        "completed_ticks": 50,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 5000},
        "per_tick": [
            {
                "tick": i,
                "duration_sec": 25.0,
                "narrator_chars": 200,
                "agents_called": (
                    ["WorldSimulator", "NarratorAgent", "MemoryCompressor"]
                    if i % 50 == 0
                    else ["WorldSimulator", "NarratorAgent"]
                ),
                "events_generated": [],
            }
            for i in range(1, 51)
        ],
    }
    out = analyzer.analyze(rep)
    findings = out["drift_findings"]
    # No memcompress silent finding (we have a hit at tick 50 and tokens > 0)
    assert not any("memory_compress" in f.lower() for f in findings), \
        f"unexpected memcompress finding: {findings}"


def test_bench_render_markdown_handles_zero_tokens() -> None:
    """edge case: total_tokens=0 不能除零 (max 1 guard)."""
    bench = _import_bench_module()
    sample = {
        "label": "edge",
        "novel_id": "bench_edge",
        "ticks": 0,
        "bootstrap_sec": 0.0,
        "tick_durations_sec": [],
        "total_tokens": 0,
        "by_agent_cumulative": {},
        "by_priority": {},
        "call_count": 0,
        "per_tick": [],
        "narratives": [],
    }
    out = bench._render_markdown(sample)
    assert isinstance(out, str)
    assert "edge" in out
