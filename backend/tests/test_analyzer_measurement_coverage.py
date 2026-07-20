from __future__ import annotations

import importlib
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

analyzer = importlib.import_module("analyze_longrange_drift")


def _ticks(n: int, **extra) -> list[dict]:
    return [
        {
            "tick": tick,
            "duration_sec": 20.0,
            "tick_total_tokens": 100,
            "agents_called": ["world_simulator", "narrator"],
            "narrator_produced": True,
            **extra,
        }
        for tick in range(1, n + 1)
    ]


def test_missing_critic_data_is_unknown_not_one_hundred_percent_clean() -> None:
    out = analyzer.analyze({"ticks": 3, "completed_ticks": 3, "per_tick": _ticks(3)})

    bucket = out["per_bucket"][0]
    assert bucket["clean_rate_pct"] is None
    assert bucket["critic_evaluated_ticks"] == 0
    assert not any("D2" in finding for finding in out["drift_findings"])


def test_short_bucket_does_not_expect_fifty_tick_compressor() -> None:
    out = analyzer.analyze({"ticks": 3, "completed_ticks": 3, "per_tick": _ticks(3)})

    assert out["per_bucket"][0]["compression_expected"] is False
    assert not any("D4" in finding for finding in out["drift_findings"])
    assert not any("D8" in finding for finding in out["drift_findings"])


def test_open_loop_snapshots_backfill_legacy_per_tick_schema() -> None:
    report = {
        "ticks": 3,
        "completed_ticks": 3,
        "per_tick": _ticks(3),
        "open_loop_snapshots": [
            {"tick": 1, "open": 6},
            {"tick": 2, "open": 6},
            {"tick": 3, "open": 5},
        ],
    }

    out = analyzer.analyze(report)
    bucket = out["per_bucket"][0]
    assert bucket["open_loop_avg"] == 5.7
    assert bucket["open_loop_at_cap_pct"] == 66.7


def test_tick_token_deltas_reconstruct_cumulative_curve_and_d6() -> None:
    per_tick = []
    for tick in range(1, 151):
        delta = 100 if tick <= 100 else 250
        per_tick.append({
            "tick": tick,
            "duration_sec": 20.0,
            "tick_total_tokens": delta,
            "agents_called": ["world_simulator", "narrator"],
            "narrator_produced": True,
        })
    out = analyzer.analyze({
        "ticks": 150,
        "completed_ticks": 150,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 1},
        "per_tick": per_tick,
    })

    assert [b["cumulative_tokens_at_end"] for b in out["per_bucket"]] == [
        5000, 10000, 22500
    ]
    assert any("D6" in finding for finding in out["drift_findings"])


def test_guardian_cumulative_contradictions_feed_d5() -> None:
    rows = _ticks(50, contradiction_count=0)
    rows[-1]["contradiction_count"] = 301
    out = analyzer.analyze({
        "ticks": 50,
        "completed_ticks": 50,
        "by_agent_cumulative": {"memory_compressor:l0_l1": 1},
        "per_tick": rows,
    })

    assert any("D5" in finding for finding in out["drift_findings"])
