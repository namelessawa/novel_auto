"""Tests for quality_metrics.longrange (Phase 2 Stage 3 — iter#86)."""

from __future__ import annotations

import pytest

from quality_metrics.longrange import (
    ForeshadowingCurve,
    MemoryFidelityReport,
    MemoryProbe,
    NoveltyDecayCurve,
    NoveltySample,
    OpenLoopSnapshot,
    foreshadowing_curve,
    memory_fidelity_report,
    novelty_decay_curve,
)


# ---------------------------------------------------------------------------
# foreshadowing
# ---------------------------------------------------------------------------


def test_foreshadowing_empty_input() -> None:
    c = foreshadowing_curve([])
    assert c.samples == []
    assert "empty_input" in c.notes
    assert c.open_to_closed_ratio_at_end == 0.0
    assert c.stale_ratio_at_end == 0.0


def test_foreshadowing_single_sample_notes_insufficient() -> None:
    c = foreshadowing_curve([OpenLoopSnapshot(tick=1, open_count=3, closed_count=0, stale_open_count=0)])
    assert any("trend_needs_more_samples" in n for n in c.notes)


def test_foreshadowing_ratios() -> None:
    """terminal sample 决定 ratio."""
    snaps = [
        OpenLoopSnapshot(tick=1, open_count=2, closed_count=0, stale_open_count=0),
        OpenLoopSnapshot(tick=10, open_count=5, closed_count=1, stale_open_count=2),
        OpenLoopSnapshot(tick=20, open_count=6, closed_count=3, stale_open_count=4),
    ]
    c = foreshadowing_curve(snaps)
    assert c.open_to_closed_ratio_at_end == pytest.approx(6 / 3)
    assert c.stale_ratio_at_end == pytest.approx(4 / 6)


def test_foreshadowing_to_dict_schema() -> None:
    c = foreshadowing_curve(
        [OpenLoopSnapshot(tick=5, open_count=3, closed_count=1, stale_open_count=1, avg_urgency=5.5)]
    )
    d = c.to_dict()
    assert d["sample_count"] == 1
    assert "open_to_closed_ratio_at_end" in d
    assert d["samples"][0]["open"] == 3
    assert d["samples"][0]["avg_urgency"] == 5.5


def test_foreshadowing_deterministic() -> None:
    snaps = [
        OpenLoopSnapshot(tick=1, open_count=2, closed_count=0, stale_open_count=0),
        OpenLoopSnapshot(tick=5, open_count=3, closed_count=1, stale_open_count=1),
    ]
    a = foreshadowing_curve(snaps).to_dict()
    b = foreshadowing_curve(snaps).to_dict()
    assert a == b


# ---------------------------------------------------------------------------
# novelty decay
# ---------------------------------------------------------------------------


def test_novelty_empty() -> None:
    c = novelty_decay_curve([])
    assert c.mean_score == 0.0
    assert c.trend == "insufficient_data"


def test_novelty_insufficient_data() -> None:
    c = novelty_decay_curve(
        [NoveltySample(tick=1, pattern_count=2, overall_score=7)]
    )
    assert c.trend == "insufficient_data"


def test_novelty_decaying_trend() -> None:
    """early 高, late 低 → decaying."""
    samples = [
        NoveltySample(tick=10, pattern_count=1, overall_score=9),
        NoveltySample(tick=20, pattern_count=1, overall_score=8),
        NoveltySample(tick=30, pattern_count=3, overall_score=6),
        NoveltySample(tick=40, pattern_count=4, overall_score=5),
    ]
    c = novelty_decay_curve(samples)
    assert c.trend == "decaying"
    assert c.mean_score == pytest.approx(7)


def test_novelty_improving_trend() -> None:
    samples = [
        NoveltySample(tick=10, pattern_count=4, overall_score=4),
        NoveltySample(tick=20, pattern_count=3, overall_score=5),
        NoveltySample(tick=30, pattern_count=2, overall_score=7),
        NoveltySample(tick=40, pattern_count=1, overall_score=8),
    ]
    c = novelty_decay_curve(samples)
    assert c.trend == "improving"


def test_novelty_stable_trend() -> None:
    samples = [
        NoveltySample(tick=10, pattern_count=2, overall_score=7),
        NoveltySample(tick=20, pattern_count=2, overall_score=7),
        NoveltySample(tick=30, pattern_count=2, overall_score=7),
        NoveltySample(tick=40, pattern_count=2, overall_score=7),
    ]
    c = novelty_decay_curve(samples)
    assert c.trend == "stable"


def test_novelty_to_dict() -> None:
    c = novelty_decay_curve(
        [NoveltySample(tick=1, pattern_count=2, overall_score=7)]
    )
    d = c.to_dict()
    assert d["sample_count"] == 1
    assert "mean_score" in d
    assert d["samples"][0]["pattern_count"] == 2


# ---------------------------------------------------------------------------
# memory fidelity
# ---------------------------------------------------------------------------


def test_memory_empty() -> None:
    r = memory_fidelity_report([])
    assert r.total_probes == 0
    assert r.lost_probes == 0
    assert r.fidelity == 0.0


def test_memory_all_found_at_l0() -> None:
    probes = [
        MemoryProbe(inject_tick=1, probe_id="p1", probe_text="x", found_in_l0=True),
        MemoryProbe(inject_tick=2, probe_id="p2", probe_text="y", found_in_l0=True),
    ]
    r = memory_fidelity_report(probes)
    assert r.fidelity == 1.0
    assert r.per_layer_count == {"l0": 2, "l1": 0, "l2": 0, "none": 0}


def test_memory_lost_probe_drops_fidelity() -> None:
    probes = [
        MemoryProbe(inject_tick=1, probe_id="p1", probe_text="x", found_in_l0=True),
        MemoryProbe(inject_tick=2, probe_id="p2", probe_text="y"),
        MemoryProbe(inject_tick=3, probe_id="p3", probe_text="z", found_in_l2=True),
    ]
    r = memory_fidelity_report(probes)
    assert r.fidelity == pytest.approx(2 / 3)
    assert r.lost_probes == 1
    assert r.per_layer_count == {"l0": 1, "l1": 0, "l2": 1, "none": 1}


def test_memory_layer_priority() -> None:
    """probe 同时 found_in_l0 + l2 → 报 l0 (最佳层)."""
    p = MemoryProbe(
        inject_tick=1, probe_id="p", probe_text="x",
        found_in_l0=True, found_in_l1=True, found_in_l2=True,
    )
    assert p.best_layer_found == "l0"


def test_memory_to_dict_schema() -> None:
    probes = [
        MemoryProbe(inject_tick=1, probe_id="p1", probe_text="x", found_in_l1=True, last_check_tick=50),
    ]
    r = memory_fidelity_report(probes)
    d = r.to_dict()
    assert d["total_probes"] == 1
    assert d["fidelity"] == 1.0
    assert d["probes"][0]["best_layer"] == "l1"


def test_memory_deterministic() -> None:
    probes = [MemoryProbe(inject_tick=1, probe_id="p1", probe_text="x", found_in_l0=True)]
    a = memory_fidelity_report(probes).to_dict()
    b = memory_fidelity_report(probes).to_dict()
    assert a == b
