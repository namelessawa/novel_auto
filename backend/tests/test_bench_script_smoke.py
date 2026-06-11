"""Smoke test for scripts/bench_tick.py.

确保 cost-quality-loop 的 bench 脚本能正常 import + 关键函数存在.
未来重构若误删 _bench / _render_markdown 等, 这个测试立即报警.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

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
