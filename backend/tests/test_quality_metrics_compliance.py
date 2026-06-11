"""Tests for quality_metrics.compliance (Phase 2 Stage 0 — iter#78)."""

from __future__ import annotations

import pytest

from quality_metrics.compliance import (
    ComplianceReport,
    NarrationRecord,
    compliance_report,
)


def _rec(
    text="x" * 800,
    tier="medium",
    flags=None,
    should=True,
) -> NarrationRecord:
    return NarrationRecord(
        text=text,
        estimated_length=tier,
        consistency_flags=flags or [],
        should_narrate=should,
    )


# ---------------------------------------------------------------------------
# 空输入
# ---------------------------------------------------------------------------


def test_empty_input() -> None:
    rep = compliance_report([])
    assert rep.total_records == 0
    assert rep.evaluated_count == 0
    assert rep.tier_hit_rate == 0.0
    assert "empty_input" in rep.notes


# ---------------------------------------------------------------------------
# Length tier 命中率
# ---------------------------------------------------------------------------


def test_perfect_tier_hit() -> None:
    """三档各一条, 全部命中范围."""
    recs = [
        _rec(text="x" * 500, tier="short"),  # 300-700
        _rec(text="x" * 900, tier="medium"),  # 600-1200
        _rec(text="x" * 1500, tier="long"),  # 1200-2200
    ]
    rep = compliance_report(recs)
    assert rep.total_records == 3
    assert rep.evaluated_count == 3
    assert rep.on_tier_count == 3
    assert rep.off_tier_count == 0
    assert rep.tier_hit_rate == 1.0


def test_off_tier_too_short() -> None:
    """tier='long' 但只写 500 字 → off."""
    rep = compliance_report([_rec(text="x" * 500, tier="long")])
    assert rep.on_tier_count == 0
    assert rep.off_tier_count == 1
    assert rep.tier_hit_rate == 0.0
    assert rep.per_tier["long"]["off"] == 1
    assert rep.per_tier["long"]["hit"] == 0


def test_off_tier_too_long() -> None:
    """tier='short' 但写 1800 字 → off (远超 700 上限)."""
    rep = compliance_report([_rec(text="x" * 1800, tier="short")])
    assert rep.off_tier_count == 1


def test_boundary_inclusive() -> None:
    """边界值: short=[300, 700] 包含两端."""
    rep = compliance_report(
        [
            _rec(text="x" * 300, tier="short"),
            _rec(text="x" * 700, tier="short"),
            _rec(text="x" * 299, tier="short"),  # 越下界
            _rec(text="x" * 701, tier="short"),  # 越上界
        ]
    )
    assert rep.on_tier_count == 2
    assert rep.off_tier_count == 2


def test_unknown_tier_noted() -> None:
    """estimated_length='none' 或未知 — 不计入命中分母, 加 note."""
    rep = compliance_report([_rec(tier="none"), _rec(tier="weird")])
    assert rep.evaluated_count == 0
    assert any("unknown_tier_count=2" in n for n in rep.notes)


# ---------------------------------------------------------------------------
# Skipped records (should_narrate=False)
# ---------------------------------------------------------------------------


def test_skipped_records_excluded_from_denominator() -> None:
    rep = compliance_report(
        [
            _rec(text="x" * 500, tier="short", should=True),
            _rec(text="", tier="none", should=False),
            _rec(text="", tier="none", should=False),
        ]
    )
    assert rep.total_records == 3
    assert rep.skipped_records == 2
    assert rep.evaluated_count == 1
    assert rep.tier_hit_rate == 1.0


# ---------------------------------------------------------------------------
# Schema violation / reasoning leak / placeholder leak
# ---------------------------------------------------------------------------


def test_schema_violation_counted() -> None:
    rep = compliance_report(
        [
            _rec(flags=["narrator_output_not_json"]),
            _rec(),
            _rec(flags=["narrator_output_not_json", "reasoning_leak"]),
        ]
    )
    assert rep.schema_violation_count == 2
    assert rep.schema_violation_rate == pytest.approx(2 / 3, abs=1e-4)


def test_reasoning_leak_counted() -> None:
    rep = compliance_report(
        [_rec(flags=["reasoning_leak"]), _rec(), _rec(flags=["reasoning_leak"])]
    )
    assert rep.reasoning_leak_count == 2
    assert rep.reasoning_leak_rate == pytest.approx(2 / 3, abs=1e-4)


def test_placeholder_leak_counted() -> None:
    rep = compliance_report([_rec(flags=["schema_placeholder_leak"]), _rec(), _rec()])
    assert rep.placeholder_leak_count == 1
    assert rep.placeholder_leak_rate == pytest.approx(1 / 3, abs=1e-4)


def test_flag_independence() -> None:
    """三个 flag 是独立 counter, 一条 record 可同时命中多个."""
    rep = compliance_report(
        [
            _rec(
                flags=[
                    "narrator_output_not_json",
                    "reasoning_leak",
                    "schema_placeholder_leak",
                ]
            )
        ]
    )
    assert rep.schema_violation_count == 1
    assert rep.reasoning_leak_count == 1
    assert rep.placeholder_leak_count == 1


# ---------------------------------------------------------------------------
# to_dict & deterministic
# ---------------------------------------------------------------------------


def test_to_dict_schema() -> None:
    rep = compliance_report([_rec(text="x" * 500, tier="short")])
    d = rep.to_dict()
    assert d["total_records"] == 1
    assert d["tier_hit_count"] == 1
    assert d["tier_hit_rate"] == 1.0
    assert d["schema_violation_rate"] == 0.0
    assert "per_tier" in d
    assert d["per_tier"]["short"]["hit"] == 1


def test_deterministic_roundtrip() -> None:
    recs = [
        _rec(text="x" * 500, tier="short", flags=["reasoning_leak"]),
        _rec(text="x" * 900, tier="medium"),
    ]
    a = compliance_report(recs).to_dict()
    b = compliance_report(recs).to_dict()
    assert a == b
