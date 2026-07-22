"""Phase 6 iter#S — Analyzer D4 per-bucket upgrade.

iter#K 把 agents_called 加进 per_tick. iter#S 把 D4 detection 从 report-level
(commit 44b6cca 临时绕过, 只看 by_agent_cumulative 总和) 升到 per-bucket
精度: 每 50-tick bucket 应至少有 1 个 tick 记录 MemoryCompressor in
agents_called.

锁定:
* 每 bucket 有 memcompress hit → 不报
* 中段 bucket 没 memcompress 但前后有 → 报 D4-perbucket
* 全程无 memcompress + tokens=0 → 仍报 report-level D4 (老逻辑)
* 全程有 memcompress 但 tokens=0 (异常) → 不报 (per-bucket 优先)
* 老 schema agents_called=[] + by_agent_cum 有 mem tokens → 不报 (兜底, 不 FP)
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import importlib  # noqa: E402

analyzer = importlib.import_module("analyze_longrange_drift")


def _bucket_with_memcompress(start_tick: int, n: int, memcompress_ticks: list[int]) -> list[dict]:
    """Generate n per_tick records starting at start_tick.

    memcompress_ticks (relative offset within bucket) get MemoryCompressor.
    """
    out = []
    for i in range(n):
        tick = start_tick + i
        agents = ["WorldSimulator", "NarratorAgent"]
        if i in memcompress_ticks:
            agents.append("MemoryCompressor")
        out.append({
            "tick": tick,
            "duration_sec": 25.0,
            "narrator_chars": 1000,
            "agents_called": agents,
            "events_generated": [],
            "narrator_produced": True,
        })
    return out


# ---------------------------------------------------------------------------
# Every bucket has memcompress → no D4 finding
# ---------------------------------------------------------------------------


def test_every_bucket_has_memcompress_no_d4() -> None:
    """5 buckets × 50 ticks, 每 bucket 1 个 memcompress tick → 不报."""
    per_tick = []
    for b in range(5):
        per_tick.extend(_bucket_with_memcompress(b * 50 + 1, 50, [25]))
    rep = {
        "label": "healthy",
        "ticks": 250,
        "completed_ticks": 250,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 5000},
        "per_tick": per_tick,
    }
    out = analyzer.analyze(rep)
    assert not any("D4" in f for f in out["drift_findings"]), \
        f"unexpected D4: {out['drift_findings']}"


# ---------------------------------------------------------------------------
# Mid-bucket silent → per-bucket D4
# ---------------------------------------------------------------------------


def test_mid_bucket_silent_triggers_perbucket_d4() -> None:
    """Bucket 2 没 memcompress (前后 bucket 有) → 报 per-bucket D4."""
    per_tick = []
    per_tick.extend(_bucket_with_memcompress(1, 50, [25]))      # bucket 0: has
    per_tick.extend(_bucket_with_memcompress(51, 50, []))        # bucket 1: NO
    per_tick.extend(_bucket_with_memcompress(101, 50, [25]))    # bucket 2: has
    rep = {
        "label": "silent-mid",
        "ticks": 150,
        "completed_ticks": 150,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 5000},
        "per_tick": per_tick,
    }
    out = analyzer.analyze(rep)
    d4_findings = [f for f in out["drift_findings"] if "D4" in f]
    assert len(d4_findings) >= 1, f"expected D4: {out['drift_findings']}"
    # 应含 bucket 信息
    assert any("t  51" in f or "bucket" in f.lower() for f in d4_findings)


# ---------------------------------------------------------------------------
# All buckets silent + zero tokens → report-level D4 (老逻辑保留)
# ---------------------------------------------------------------------------


def test_all_silent_zero_tokens_reports_level_d4() -> None:
    per_tick = []
    for b in range(3):
        per_tick.extend(_bucket_with_memcompress(b * 50 + 1, 50, []))
    rep = {
        "label": "all-silent",
        "ticks": 150,
        "completed_ticks": 150,
        "by_agent_cumulative": {},  # 0 mem tokens
        "per_tick": per_tick,
    }
    out = analyzer.analyze(rep)
    d4_findings = [f for f in out["drift_findings"] if "D4" in f]
    assert len(d4_findings) >= 1


# ---------------------------------------------------------------------------
# Backward compat: 老 schema agents_called=[] + by_agent has tokens → 不 FP
# ---------------------------------------------------------------------------


def test_legacy_schema_with_tokens_no_d4() -> None:
    """老 bench JSON: per_tick.agents_called=[] (空) + by_agent_cum 有 mem tokens.

    不应报 per-bucket D4 (会全报 FP), report-level 兜底也不报 (有 tokens).
    """
    per_tick = []
    for b in range(5):
        for i in range(50):
            per_tick.append({
                "tick": b * 50 + i + 1,
                "duration_sec": 25.0,
                "narrator_chars": 1000,
                "agents_called": [],  # 老 schema 全空
                "events_generated": [],
            })
    rep = {
        "label": "legacy",
        "ticks": 250,
        "completed_ticks": 250,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 5000},
        "per_tick": per_tick,
    }
    out = analyzer.analyze(rep)
    assert not any("D4" in f for f in out["drift_findings"]), \
        f"unexpected FP on legacy schema: {out['drift_findings']}"
