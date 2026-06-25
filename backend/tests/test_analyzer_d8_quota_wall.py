"""Phase 6 iter#TTT — D8 quota wall detection in drift analyzer.

Phase 6-A Run 1 (24 日) + Republic_spy (25 日) 都触底 DeepSeek quota,
后段 tick avg_dur 跌到 0.3-0.7s (LLM 返回 429 立即, orchestrator 仍跑 7
阶段但 no-op). 老 analyzer 没显式 flag, 这会污染:
* D1 avg_dur drift (低速 bucket 看似 PASS)
* D7 narrate-rate cascade (无 narrative 0% rate)

D8 显式: ≥1 个 bucket avg_dur < 5s 且 narrate_rate < 5% → quota wall.

锁定:
* 健康 bucket → 不报
* tail 多 bucket 低速低 narrate → D8
* 中段一个 bucket 低速低 narrate → 仍 D8 (但 evidence 提示位置)
* 老 schema 无 narrate_rate → fallback 只看 avg_dur
* env knob D8_AVG_DUR_MAX / D8_NARRATE_MAX 自定义
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import importlib

analyzer = importlib.import_module("analyze_longrange_drift")


def _make_report(durs_and_rates: list[tuple[float, float]]) -> dict:
    """Build a synthetic 50-tick-bucket report.

    durs_and_rates: list of (avg_dur, narrate_rate) per bucket.
    """
    per_tick = []
    for bi, (dur, rate) in enumerate(durs_and_rates):
        bucket_start = bi * 50 + 1
        for offset in range(50):
            tick = bucket_start + offset
            produced = (offset / 50) < rate
            per_tick.append({
                "tick": tick,
                "duration_sec": dur,
                "narrator_chars": 1000 if produced else 0,
                "agents_called": ["WorldSimulator", "NarratorAgent"],
                "events_generated": [],
                "narrator_produced": produced,
            })
    return {
        "label": "synth",
        "ticks": len(durs_and_rates) * 50,
        "completed_ticks": len(durs_and_rates) * 50,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 5000},
        "per_tick": per_tick,
    }


# ---------------------------------------------------------------------------
# Healthy: no D8
# ---------------------------------------------------------------------------


def test_healthy_no_d8() -> None:
    """全 bucket avg_dur > 5s + narrate ~ 0.4 → 不报 D8."""
    rep = _make_report([(25.0, 0.44)] * 5)
    out = analyzer.analyze(rep)
    assert not any("[D8]" in f for f in out["drift_findings"])


# ---------------------------------------------------------------------------
# Tail quota wall: 3+ buckets at end with low dur + low narrate
# ---------------------------------------------------------------------------


def test_tail_quota_wall_triggers_d8() -> None:
    """Phase 6-A Run 1 pattern: 前 3 bucket 健康, 后 2 quota-degenerate."""
    rep = _make_report([
        (25.0, 0.44),  # healthy
        (28.0, 0.46),  # healthy
        (25.0, 0.42),  # healthy
        (0.4, 0.0),    # quota wall
        (0.3, 0.0),    # quota wall
    ])
    out = analyzer.analyze(rep)
    d8 = [f for f in out["drift_findings"] if "[D8]" in f]
    assert len(d8) >= 1, f"expected D8: {out['drift_findings']}"


def test_single_bucket_quota_wall_triggers() -> None:
    rep = _make_report([
        (25.0, 0.44),
        (0.5, 0.02),  # tiny but qualifies
        (25.0, 0.40),
    ])
    out = analyzer.analyze(rep)
    assert any("[D8]" in f for f in out["drift_findings"])


# ---------------------------------------------------------------------------
# Edge: low dur but high narrate → NOT quota wall (fast natural rhythm)
# ---------------------------------------------------------------------------


def test_low_dur_high_narrate_not_quota_wall() -> None:
    """avg_dur 3s 但 narrate 50% → 不是 quota wall (可能 cache hit)."""
    rep = _make_report([
        (3.0, 0.50),
        (25.0, 0.44),
    ])
    out = analyzer.analyze(rep)
    assert not any("[D8]" in f for f in out["drift_findings"])


def test_high_dur_low_narrate_not_quota_wall() -> None:
    """avg_dur 25s 但 narrate 5% → silent ticks, 不是 quota wall."""
    rep = _make_report([
        (25.0, 0.05),
        (25.0, 0.44),
    ])
    out = analyzer.analyze(rep)
    assert not any("[D8]" in f for f in out["drift_findings"])


# ---------------------------------------------------------------------------
# Env knobs
# ---------------------------------------------------------------------------


def test_d8_custom_avg_dur_threshold(monkeypatch) -> None:
    monkeypatch.setenv("D8_AVG_DUR_MAX", "10")
    rep = _make_report([
        (25.0, 0.44),
        (8.0, 0.02),  # 8 < 10 + narrate < 5%
    ])
    out = analyzer.analyze(rep)
    assert any("[D8]" in f for f in out["drift_findings"])


def test_d8_disabled_via_env(monkeypatch) -> None:
    monkeypatch.setenv("D8_AVG_DUR_MAX", "0")
    rep = _make_report([(25.0, 0.44), (0.3, 0.0)])
    out = analyzer.analyze(rep)
    # D8 disabled
    assert not any("[D8]" in f for f in out["drift_findings"])


# ---------------------------------------------------------------------------
# Legacy schema (no narrator_produced)
# ---------------------------------------------------------------------------


def test_legacy_schema_d8_falls_back_to_avg_dur_only() -> None:
    """老 bench 无 narrator_produced → narrate_rate=None, 仅按 avg_dur 判."""
    rep = {
        "label": "legacy",
        "ticks": 100,
        "completed_ticks": 100,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 5000},
        "per_tick": [
            {"tick": i, "duration_sec": 25.0, "narrator_chars": 1000}
            for i in range(1, 51)
        ] + [
            {"tick": i, "duration_sec": 0.3, "narrator_chars": 0}
            for i in range(51, 101)
        ],
    }
    out = analyzer.analyze(rep)
    # 老 schema 仍 catch quota wall via avg_dur
    assert any("[D8]" in f for f in out["drift_findings"])
