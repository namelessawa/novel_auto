"""Phase 5-B boundary tests for world_stale_detector.

5 boundary cases pin the det layer logic. Real bench validates skip rate
in production; these tests pin the predicate behavior so a future change
can't silently flip a condition.
"""

from __future__ import annotations

import pytest

from memory_system.models import Event
from nf_core.world_stale_detector import (
    StaleDecision,
    evaluate_stale,
)


def _make_event(
    value: int = 1,
    type_: str = "exogenous",
    description: str = "",
    tick: int = 5,
    location: str = "loc_a",
) -> Event:
    return Event(
        id=f"evt_{type_}_{value}_{tick}",
        type=type_,
        tick=tick,
        description=description or f"test {type_} v{value}",
        narrative_value=value,
        narrative_value_hint=value,
        location=location,
    )


# Case 1 — all conditions met → stale ----------------------------------------


def test_all_stale_conditions_met_yields_skip() -> None:
    events = [
        _make_event(value=2, type_="exogenous", description="风停了"),
        _make_event(value=3, type_="exogenous", description="远处灯灭"),
    ]
    decision = evaluate_stale(
        current_world_time=10,
        last_llm_world_time=8,  # only 2 ticks since LLM
        last_tick_events=events,
    )
    assert isinstance(decision, StaleDecision)
    assert decision.should_skip is True
    assert "stale" in decision.reason


# Case 2 — high-value event present → NOT stale ------------------------------


def test_high_value_event_blocks_skip() -> None:
    events = [
        _make_event(value=2),
        _make_event(value=7, description="重大冲突"),  # >= 5 cap
    ]
    decision = evaluate_stale(
        current_world_time=10,
        last_llm_world_time=8,
        last_tick_events=events,
    )
    assert decision.should_skip is False
    assert "high_value_event" in decision.reason


def test_narrative_value_hint_also_counts() -> None:
    """hint 字段也算 — EventInjector 在 inject 时给 hint, 后续 resolver 给 value."""
    e = Event(
        id="evt_hint",
        type="exogenous",
        tick=5,
        description="hint-driven",
        narrative_value=0,
        narrative_value_hint=6,  # hint 触发 cap
    )
    decision = evaluate_stale(
        current_world_time=10,
        last_llm_world_time=8,
        last_tick_events=[e],
    )
    assert decision.should_skip is False
    assert "high_value_event" in decision.reason


# Case 3 — high-impact (dramatic) event blocks skip --------------------------
# 本仓 Event.type 是 Literal[endogenous, exogenous, dramatic, character_action].
# 'dramatic' 是 EventInjector / Showrunner 给场景节拍 / 重大冲突的标.


def test_dramatic_event_blocks_skip() -> None:
    events = [
        _make_event(value=2),
        _make_event(value=3, type_="dramatic", description="幕间冲突"),
    ]
    decision = evaluate_stale(
        current_world_time=10,
        last_llm_world_time=8,
        last_tick_events=events,
    )
    assert decision.should_skip is False
    assert "high_impact_event_present" in decision.reason


def test_low_value_dramatic_still_blocks_skip() -> None:
    """即使 narrative_value=1 但 type=dramatic, 也不 skip — dramatic 标本身是信号."""
    events = [_make_event(value=1, type_="dramatic")]
    decision = evaluate_stale(
        current_world_time=10,
        last_llm_world_time=8,
        last_tick_events=events,
    )
    assert decision.should_skip is False
    assert "high_impact_event_present" in decision.reason


def test_endogenous_low_value_does_not_block() -> None:
    """常规 endogenous / exogenous 低价值事件不 block."""
    events = [
        _make_event(value=2, type_="endogenous"),
        _make_event(value=1, type_="exogenous"),
        _make_event(value=3, type_="character_action"),
    ]
    decision = evaluate_stale(
        current_world_time=10,
        last_llm_world_time=8,
        last_tick_events=events,
    )
    assert decision.should_skip is True


# Case 4 — consecutive skip cap forces refresh -------------------------------


def test_force_refresh_after_max_consecutive_skip() -> None:
    """距上次 LLM 调用 >= max_consecutive_skip → 必须跑 LLM."""
    events = [_make_event(value=1)]
    # last_llm_world_time=5, current=8 → ticks_since_llm=3 >= 3 → force refresh
    decision = evaluate_stale(
        current_world_time=8,
        last_llm_world_time=5,
        last_tick_events=events,
        max_consecutive_skip=3,
    )
    assert decision.should_skip is False
    assert "force_refresh" in decision.reason
    assert "3_ticks_since_llm" in decision.reason


def test_just_below_max_skip_still_stale() -> None:
    events = [_make_event(value=1)]
    decision = evaluate_stale(
        current_world_time=7,  # ticks_since_llm = 2 (< 3)
        last_llm_world_time=5,
        last_tick_events=events,
        max_consecutive_skip=3,
    )
    assert decision.should_skip is True


# Case 5 — cold start (no prior LLM call) → NOT stale (defensive) -----------


def test_cold_start_must_run_llm() -> None:
    """WorldSimulator 第一次跑必须建立基线, 不能 skip."""
    decision = evaluate_stale(
        current_world_time=1,
        last_llm_world_time=-1,  # never called
        last_tick_events=[],
    )
    assert decision.should_skip is False
    assert "cold_start" in decision.reason


# Bonus — empty events list is stale (no signal at all) ---------------------


def test_empty_events_list_is_stale() -> None:
    """没事件本身就是 stale 信号 — 没素材逼世界 LLM 没意义."""
    decision = evaluate_stale(
        current_world_time=10,
        last_llm_world_time=9,
        last_tick_events=[],
    )
    assert decision.should_skip is True


# Bonus — env override --------------------------------------------------------


def test_env_override_value_cap(monkeypatch) -> None:
    """WORLD_STALE_VALUE_CAP=10 让 narrative_value=7 不再 block skip."""
    monkeypatch.setenv("WORLD_STALE_VALUE_CAP", "10")
    events = [_make_event(value=7)]  # 7 < 10 → not high-value
    decision = evaluate_stale(
        current_world_time=10,
        last_llm_world_time=9,
        last_tick_events=events,
    )
    assert decision.should_skip is True


def test_env_override_max_consecutive_skip(monkeypatch) -> None:
    """WORLD_STALE_MAX_SKIP=10 把 force-refresh 推迟."""
    monkeypatch.setenv("WORLD_STALE_MAX_SKIP", "10")
    events = [_make_event(value=1)]
    decision = evaluate_stale(
        current_world_time=15,  # ticks_since_llm = 8 < 10
        last_llm_world_time=7,
        last_tick_events=events,
    )
    assert decision.should_skip is True


def test_stale_decision_truthy_protocol() -> None:
    """if decision: 应等价 if decision.should_skip — 便于 caller 单 line 判."""
    d_stale = StaleDecision(True, "ok")
    d_run = StaleDecision(False, "force")
    assert bool(d_stale) is True
    assert bool(d_run) is False
    if d_stale:
        pass
    else:
        pytest.fail("StaleDecision truthy protocol broken")
