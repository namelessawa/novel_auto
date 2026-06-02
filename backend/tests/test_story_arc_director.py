"""Tests for StoryArcDirector — 节奏曲线 / 节拍守护 / directive 生成。"""

from __future__ import annotations

import pytest

from agents.story_arc_director import (
    EXPECTED_INTENSITY_CURVE,
    FLAT_PACING_THRESHOLD,
    HIGH_PACING_FATIGUE,
    PACING_HISTORY_MAX,
    StoryArcDirector,
)
from memory_system.models import (
    KeyBeat,
    PacingPoint,
    StoryArc,
)


def _arc(
    *,
    theme: str = "在守护中遗失",
    target_climax: int = 100,
    beats: list[KeyBeat] | None = None,
    pacing: list[PacingPoint] | None = None,
    title: str = "灯塔",
) -> StoryArc:
    return StoryArc(
        title=title,
        theme=theme,
        central_question="人能守护一件正在崩坏的东西吗?",
        target_climax_tick=target_climax,
        key_beats=beats or [],
        pacing_history=pacing or [],
    )


def _beat(
    bid: str,
    *,
    title: str = "",
    window: tuple[int, int] = (0, 100),
    status: str = "pending",
) -> KeyBeat:
    return KeyBeat(
        id=bid,
        title=title or bid,
        description=f"{bid} 戏剧目标",
        window_start=window[0],
        window_end=window[1],
        status=status,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# 节奏曲线 (确定性)
# ---------------------------------------------------------------------------


def test_progress_ratio_clamps() -> None:
    d = StoryArcDirector()
    assert d._progress_ratio(0, 100) == 0.0
    assert d._progress_ratio(50, 100) == 0.5
    assert d._progress_ratio(150, 100) == 1.0
    assert d._progress_ratio(10, 0) == 0.0


def test_expected_intensity_follows_curve() -> None:
    d = StoryArcDirector()
    # 0% → low (≤ 0.10)
    assert d._expected_intensity_for(0.05) == "low"
    # 30% → medium (≤ 0.50)
    assert d._expected_intensity_for(0.30) == "medium"
    # 60% → high (≤ 0.65)
    assert d._expected_intensity_for(0.60) == "high"
    # 100% → climax
    assert d._expected_intensity_for(1.0) == "climax"


def test_pacing_streaks() -> None:
    d = StoryArcDirector()
    # 末尾 5 个 low
    history = [PacingPoint(tick=i, intensity="low") for i in range(5)]
    flat, high = d._pacing_streaks(history)
    assert flat == 5
    assert high == 0

    # 末尾 3 个 high
    history = [PacingPoint(tick=i, intensity="high") for i in range(3)]
    flat, high = d._pacing_streaks(history)
    assert flat == 0
    assert high == 3

    # 末尾混合: low low medium → flat=0 (被 medium 阻断)
    history = [
        PacingPoint(tick=0, intensity="low"),
        PacingPoint(tick=1, intensity="low"),
        PacingPoint(tick=2, intensity="medium"),
    ]
    flat, high = d._pacing_streaks(history)
    assert flat == 0
    assert high == 0


def test_sample_intensity_buckets() -> None:
    d = StoryArcDirector
    assert d._sample_intensity(0, "medium") == "low"
    assert d._sample_intensity(10, "medium") == "medium"
    assert d._sample_intensity(20, "medium") == "high"
    assert d._sample_intensity(40, "medium") == "climax"


# ---------------------------------------------------------------------------
# Beat 状态分析
# ---------------------------------------------------------------------------


def test_analyze_detects_overdue_beats() -> None:
    arc = _arc(beats=[_beat("b1", window=(0, 10))])
    d = StoryArcDirector()
    analysis = d.analyze(arc=arc, current_tick=20, recent_events=[])
    assert "b1" in analysis.overdue_beat_ids


def test_analyze_picks_active_beat() -> None:
    arc = _arc(
        beats=[
            _beat("b1", status="completed"),
            _beat("b2", status="active"),
            _beat("b3", status="pending", window=(50, 100)),
        ]
    )
    d = StoryArcDirector()
    analysis = d.analyze(arc=arc, current_tick=10, recent_events=[])
    assert analysis.active_beat is not None
    assert analysis.active_beat.id == "b2"


def test_analyze_picks_next_pending_in_window() -> None:
    arc = _arc(
        beats=[
            _beat("b1", status="completed"),
            _beat("b2", status="pending", window=(0, 20)),
            _beat("b3", status="pending", window=(30, 50)),
        ]
    )
    d = StoryArcDirector()
    analysis = d.analyze(arc=arc, current_tick=10, recent_events=[])
    assert analysis.next_beat is not None
    assert analysis.next_beat.id == "b2"


# ---------------------------------------------------------------------------
# direct() — 主入口集成
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_direct_flat_streak_recommends_escalation(mock_llm) -> None:
    pacing = [PacingPoint(tick=i, intensity="low") for i in range(FLAT_PACING_THRESHOLD)]
    arc = _arc(pacing=pacing)
    d = StoryArcDirector(enable_llm=False)
    directive = await d.direct(
        arc=arc, current_tick=10, recent_events=[], recent_narrator_value_sum=0
    )
    assert directive.needs_escalation is True
    assert directive.suspense_pool_health == "background"


@pytest.mark.asyncio
async def test_direct_high_streak_recommends_breather(mock_llm) -> None:
    pacing = [PacingPoint(tick=i, intensity="high") for i in range(HIGH_PACING_FATIGUE)]
    arc = _arc(pacing=pacing)
    d = StoryArcDirector(enable_llm=False)
    directive = await d.direct(
        arc=arc, current_tick=20, recent_events=[], recent_narrator_value_sum=20
    )
    assert directive.needs_breather is True
    assert directive.suspense_pool_health == "peaking"


@pytest.mark.asyncio
async def test_direct_appends_pacing_point(mock_llm) -> None:
    arc = _arc()
    d = StoryArcDirector(enable_llm=False)
    await d.direct(
        arc=arc, current_tick=5, recent_events=[], recent_narrator_value_sum=8
    )
    assert len(arc.pacing_history) == 1
    assert arc.pacing_history[0].tick == 5
    assert arc.pacing_history[0].intensity == "medium"


@pytest.mark.asyncio
async def test_direct_caps_pacing_history(mock_llm, monkeypatch) -> None:
    # 把历史填到上限附近, 再 direct 一次, 老的会被弹出
    pacing = [PacingPoint(tick=i, intensity="medium") for i in range(PACING_HISTORY_MAX)]
    arc = _arc(pacing=pacing)
    d = StoryArcDirector(enable_llm=False)
    await d.direct(
        arc=arc, current_tick=PACING_HISTORY_MAX, recent_events=[], recent_narrator_value_sum=8
    )
    assert len(arc.pacing_history) == PACING_HISTORY_MAX


@pytest.mark.asyncio
async def test_direct_overdue_beat_listed(mock_llm) -> None:
    arc = _arc(beats=[_beat("b1", window=(0, 5))])
    d = StoryArcDirector(enable_llm=False)
    directive = await d.direct(
        arc=arc, current_tick=20, recent_events=[], recent_narrator_value_sum=0
    )
    assert "b1" in directive.overdue_beats


@pytest.mark.asyncio
async def test_direct_active_beat_id_returned(mock_llm) -> None:
    arc = _arc(beats=[_beat("b1", status="active")])
    d = StoryArcDirector(enable_llm=False)
    directive = await d.direct(
        arc=arc, current_tick=5, recent_events=[], recent_narrator_value_sum=8
    )
    assert directive.active_beat_id == "b1"


@pytest.mark.asyncio
async def test_direct_no_theme_no_llm_no_hint(mock_llm) -> None:
    arc = _arc(theme="", title="无主题")
    arc.central_question = ""
    d = StoryArcDirector(enable_llm=False)
    directive = await d.direct(
        arc=arc, current_tick=5, recent_events=[], recent_narrator_value_sum=8
    )
    assert directive.theme_reminder == ""
    assert directive.narrator_hint == ""


@pytest.mark.asyncio
async def test_direct_fallback_hint_when_llm_off(mock_llm) -> None:
    arc = _arc(theme="在守护中遗失", beats=[_beat("b1", title="第一次裂痕")])
    d = StoryArcDirector(enable_llm=False)
    directive = await d.direct(
        arc=arc, current_tick=5, recent_events=[], recent_narrator_value_sum=8
    )
    assert "主题" in directive.theme_reminder
    assert "第一次裂痕" in directive.narrator_hint


@pytest.mark.asyncio
async def test_direct_llm_path(mock_llm) -> None:
    mock_llm.set_responses(
        [
            {
                "theme_reminder": "主题:守护与崩坏并行",
                "narrator_hint": "本段聚焦灯塔基石的细微裂纹, 不要描述天气",
                "diagnosis": "节奏接近期待值",
            }
        ]
    )
    arc = _arc()
    d = StoryArcDirector(enable_llm=True)
    directive = await d.direct(
        arc=arc, current_tick=10, recent_events=[], recent_narrator_value_sum=12
    )
    assert "守护" in directive.theme_reminder
    assert "灯塔基石" in directive.narrator_hint


@pytest.mark.asyncio
async def test_direct_progress_drives_expected_intensity(mock_llm) -> None:
    arc = _arc(target_climax=100)
    d = StoryArcDirector(enable_llm=False)
    # tick=98 → progress=98% → expected=climax
    directive = await d.direct(
        arc=arc, current_tick=98, recent_events=[], recent_narrator_value_sum=10
    )
    assert directive.intensity_recommendation == "climax"
