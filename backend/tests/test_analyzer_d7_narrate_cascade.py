"""Phase 6 iter#Z — Drift analyzer D7: narrate-rate cascade detection.

Phase 6-A run 1 (24 日 bench) 真实问题: t201 起进入 100% narrate stuck-state
4-5 个 bucket 到 quota wall. iter#M 是预防 (生产 guard), iter#Z 是检测
(post-hoc analyzer flag).

定义: D7 cascade = ≥ 2 个 consecutive bucket narrate_rate ≥ 0.7 (默认).
意图: 单个 spike bucket 不报 (合理 climax), 但 2+ 连续 = stuck pattern.

数据来源: per_tick.narrator_produced (iter#K 已加).

锁定:
* 正常 narrate_rate (~44%) → 不报
* 单 bucket spike (其中一个 100%, 邻居 44%) → 不报
* 2 连续 bucket ≥ 70% → 报 D7
* 3 连续 bucket → 报 D7 (含连续 count)
* env 自定义阈值 (D7_THRESHOLD, D7_MIN_BUCKETS)
* per_tick 没有 narrator_produced 字段 (老 schema) → skip D7 不报
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


def _make_report(narrate_rates: list[float], n_per_bucket: int = 50) -> dict:
    """Build a synthetic 50-tick-bucket report with given narrate_rate per bucket."""
    per_tick = []
    for bi, rate in enumerate(narrate_rates):
        bucket_start = bi * n_per_bucket + 1
        for offset in range(n_per_bucket):
            tick = bucket_start + offset
            # Distribute narrator_produced=True according to rate
            produced = (offset / n_per_bucket) < rate
            per_tick.append({
                "tick": tick,
                "duration_sec": 25.0,
                "narrator_chars": 1000 if produced else 0,
                "agents_called": ["WorldSimulator", "NarratorAgent"],
                "events_generated": [],
                "narrator_produced": produced,
            })
    return {
        "label": "synth",
        "ticks": len(narrate_rates) * n_per_bucket,
        "completed_ticks": len(narrate_rates) * n_per_bucket,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 5000},
        "per_tick": per_tick,
    }


# ---------------------------------------------------------------------------
# Normal cases: no D7
# ---------------------------------------------------------------------------


def test_normal_narrate_rate_no_d7() -> None:
    """All buckets ~44% narrate → 不报 D7."""
    rep = _make_report([0.44, 0.46, 0.42, 0.48, 0.44])
    out = analyzer.analyze(rep)
    findings = out["drift_findings"]
    assert not any("[D7]" in f for f in findings), \
        f"unexpected D7: {findings}"


def test_single_bucket_spike_no_d7() -> None:
    """单 bucket 100% narrate, 邻居 44% → 单 spike 不报 D7 (允许 climax)."""
    rep = _make_report([0.44, 0.46, 1.0, 0.44, 0.42])
    out = analyzer.analyze(rep)
    assert not any("[D7]" in f for f in out["drift_findings"])


# ---------------------------------------------------------------------------
# D7 trigger cases
# ---------------------------------------------------------------------------


def test_two_consecutive_high_buckets_triggers_d7() -> None:
    """t201/t251 双 bucket 100% narrate → D7."""
    rep = _make_report([0.44, 0.44, 1.0, 1.0, 0.44])
    out = analyzer.analyze(rep)
    d7_findings = [f for f in out["drift_findings"] if "[D7]" in f]
    assert len(d7_findings) >= 1, f"expected D7 trigger: {out['drift_findings']}"


def test_three_consecutive_high_buckets_triggers_d7() -> None:
    """Run 1 pattern: t201-300 全 100% narrate → D7."""
    rep = _make_report([0.44, 0.44, 1.0, 1.0, 1.0, 0.44])
    out = analyzer.analyze(rep)
    d7_findings = [f for f in out["drift_findings"] if "[D7]" in f]
    assert len(d7_findings) >= 1
    # evidence 应含 bucket 数信息
    assert any("3" in f or "consecutive" in f.lower() for f in d7_findings)


def test_d7_threshold_just_below_no_trigger() -> None:
    """两个 65% bucket < 默认 70% 阈值 → 不报."""
    rep = _make_report([0.44, 0.44, 0.65, 0.65, 0.44])
    out = analyzer.analyze(rep)
    assert not any("[D7]" in f for f in out["drift_findings"])


def test_d7_threshold_at_70_pct_triggers() -> None:
    """两个 75% bucket ≥ 70% → 报."""
    rep = _make_report([0.44, 0.44, 0.75, 0.75, 0.44])
    out = analyzer.analyze(rep)
    assert any("[D7]" in f for f in out["drift_findings"])


# ---------------------------------------------------------------------------
# Env knobs
# ---------------------------------------------------------------------------


def test_d7_custom_threshold(monkeypatch) -> None:
    """D7_THRESHOLD=0.5 + 两个 55% bucket → 报."""
    monkeypatch.setenv("D7_NARRATE_THRESHOLD", "0.5")
    rep = _make_report([0.44, 0.44, 0.55, 0.55, 0.44])
    out = analyzer.analyze(rep)
    assert any("[D7]" in f for f in out["drift_findings"])


def test_d7_custom_min_buckets(monkeypatch) -> None:
    """D7_MIN_BUCKETS=3 + 仅 2 个 75% bucket → 不报 (因 cascade 长度不够)."""
    monkeypatch.setenv("D7_MIN_BUCKETS", "3")
    rep = _make_report([0.44, 0.75, 0.75, 0.44])
    out = analyzer.analyze(rep)
    assert not any("[D7]" in f for f in out["drift_findings"])


# ---------------------------------------------------------------------------
# Backward compat: per_tick 无 narrator_produced (老 schema)
# ---------------------------------------------------------------------------


def test_d7_skipped_when_schema_missing() -> None:
    """老 bench JSON 无 narrator_produced 字段 → 不报 D7, 不抛."""
    rep = {
        "label": "legacy",
        "ticks": 100,
        "completed_ticks": 100,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 5000},
        "per_tick": [
            {
                "tick": i,
                "duration_sec": 25.0,
                "narrator_chars": 1000,
                # NO narrator_produced field
            }
            for i in range(1, 101)
        ],
    }
    out = analyzer.analyze(rep)
    # 应不抛, 不报 D7
    assert not any("[D7]" in f for f in out["drift_findings"])
