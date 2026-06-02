"""Tests for CharacterArcTracker — 确定性检测 + LLM 合并 + B 级配角守护。"""

from __future__ import annotations

import pytest

from agents.character_arc_tracker import (
    ARC_STAGE_ORDER,
    EXPECTED_PROGRESS_PER_STAGE,
    STALLED_TICKS,
    CharacterArcTracker,
)
from memory_system.models import (
    CharacterAction,
    CharacterProfile,
    CharacterState,
)


def _profile(
    cid: str = "alice",
    tier: str = "A",
    speech: str = "短句, 反问多",
    personality: str = "克制, 冷静",
) -> CharacterProfile:
    return CharacterProfile(
        id=cid,
        name=cid,
        age=30,
        role="主角",
        importance_tier=tier,  # type: ignore[arg-type]
        personality=personality,
        speech_style=speech,
    )


def _state(
    cid: str = "alice",
    arc_stage: str = "起点",
    arc_progress: float = 0.0,
    entered_tick: int = 0,
    agenda: list[str] | None = None,
    fingerprint: list[str] | None = None,
) -> CharacterState:
    return CharacterState(
        character_id=cid,
        arc_stage=arc_stage,  # type: ignore[arg-type]
        arc_progress=arc_progress,
        arc_stage_entered_tick=entered_tick,
        independent_agenda=agenda or [],
        speech_fingerprint_features=fingerprint or [],
    )


# ---------------------------------------------------------------------------
# 确定性检测
# ---------------------------------------------------------------------------


def test_detect_progress_mismatch_true_when_above_window() -> None:
    s = _state(arc_stage="起点", arc_progress=0.5)
    assert CharacterArcTracker.detect_progress_mismatch(s) is True


def test_detect_progress_mismatch_false_in_window() -> None:
    s = _state(arc_stage="觉醒", arc_progress=0.2)
    assert CharacterArcTracker.detect_progress_mismatch(s) is False


def test_detect_stalled_true_after_threshold() -> None:
    s = _state(arc_stage="觉醒", entered_tick=0)
    assert CharacterArcTracker.detect_stalled(s, current_tick=STALLED_TICKS + 1) is True


def test_detect_stalled_false_in_end_stage() -> None:
    s = _state(arc_stage="结局", entered_tick=0)
    assert CharacterArcTracker.detect_stalled(s, current_tick=10_000) is False


def test_detect_agenda_health_b_tier_empty_triggers() -> None:
    p = _profile(tier="B")
    s = _state(agenda=[])
    assert CharacterArcTracker.detect_agenda_health(p, s) == "empty"


def test_detect_agenda_health_a_tier_always_ok() -> None:
    p = _profile(tier="A")
    s = _state(agenda=[])
    assert CharacterArcTracker.detect_agenda_health(p, s) == "ok"


def test_suggest_next_stage_advances_on_overage() -> None:
    s = _state(arc_stage="起点", arc_progress=0.25)
    assert CharacterArcTracker.suggest_next_stage(s) == "觉醒"


def test_suggest_next_stage_none_in_range() -> None:
    s = _state(arc_stage="觉醒", arc_progress=0.20)
    assert CharacterArcTracker.suggest_next_stage(s) is None


# ---------------------------------------------------------------------------
# deterministic_report
# ---------------------------------------------------------------------------


def test_deterministic_report_b_tier_empty_agenda_drifts_b3() -> None:
    tracker = CharacterArcTracker(enable_llm=False)
    p = _profile(cid="bob", tier="B")
    s = _state(cid="bob")
    rep = tracker.deterministic_report(profile=p, state=s, current_tick=10)
    assert "B3" in rep.drift_codes
    assert rep.independent_agenda_health == "empty"


def test_deterministic_report_stalled_triggers_evidence() -> None:
    tracker = CharacterArcTracker(enable_llm=False)
    p = _profile()
    s = _state(arc_stage="觉醒", entered_tick=0)
    rep = tracker.deterministic_report(
        profile=p, state=s, current_tick=STALLED_TICKS + 5
    )
    assert rep.is_stalled is True
    assert any("停留" in e for e in rep.drift_evidence)


# ---------------------------------------------------------------------------
# evaluate() 主入口
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_filters_to_a_b_tier(mock_llm) -> None:
    tracker = CharacterArcTracker(enable_llm=False)
    profiles = {
        "alice": _profile(cid="alice", tier="A"),
        "bob": _profile(cid="bob", tier="B"),
        "npc": _profile(cid="npc", tier="C"),
    }
    states = {cid: _state(cid=cid) for cid in profiles}
    out = await tracker.evaluate(
        profiles=profiles,
        states=states,
        recent_actions_by_char={},
        current_tick=10,
    )
    ids = {r.character_id for r in out.reports}
    assert ids == {"alice", "bob"}  # C 级不评估


@pytest.mark.asyncio
async def test_evaluate_summary_lists_drift_and_stalled(mock_llm) -> None:
    tracker = CharacterArcTracker(enable_llm=False)
    profiles = {
        "bob": _profile(cid="bob", tier="B"),  # 缺议程 → B3 漂移
        "alice": _profile(cid="alice", tier="A"),
    }
    states = {
        "bob": _state(cid="bob"),
        "alice": _state(cid="alice", arc_stage="觉醒", entered_tick=0),
    }
    out = await tracker.evaluate(
        profiles=profiles,
        states=states,
        recent_actions_by_char={},
        current_tick=STALLED_TICKS + 5,
    )
    assert "停滞" in out.summary
    assert "无议程" in out.summary
    assert "bob" in out.drift_ids()
    assert "alice" in out.stalled_ids()


@pytest.mark.asyncio
async def test_evaluate_llm_merges_drift_codes(mock_llm) -> None:
    mock_llm.set_responses(
        [
            {
                "reports": [
                    {
                        "character_id": "alice",
                        "drift_codes": ["B5"],
                        "drift_evidence": ["最近 5 个行动全部成功"],
                        "suggested_stage": "觉醒",
                        "speech_compliance": "ok",
                        "rationale": "需要一次明显的判断失误",
                    }
                ],
                "summary": "主角弧光稳健但缺乏失误",
            }
        ]
    )
    tracker = CharacterArcTracker(enable_llm=True)
    profiles = {"alice": _profile(cid="alice", tier="A")}
    states = {"alice": _state(cid="alice")}
    out = await tracker.evaluate(
        profiles=profiles,
        states=states,
        recent_actions_by_char={"alice": []},
        current_tick=10,
    )
    rep = next(r for r in out.reports if r.character_id == "alice")
    assert "B5" in rep.drift_codes
    assert rep.suggested_stage == "觉醒"
    assert rep.speech_compliance == "ok"


@pytest.mark.asyncio
async def test_evaluate_full_clean_returns_empty_drift(mock_llm) -> None:
    tracker = CharacterArcTracker(enable_llm=False)
    profiles = {
        "alice": _profile(cid="alice", tier="A"),
        "bob": _profile(cid="bob", tier="B"),
    }
    states = {
        "alice": _state(cid="alice", arc_stage="起点", arc_progress=0.1),
        "bob": _state(
            cid="bob",
            arc_stage="起点",
            arc_progress=0.1,
            agenda=["复仇", "守护妹妹"],
        ),
    }
    out = await tracker.evaluate(
        profiles=profiles,
        states=states,
        recent_actions_by_char={},
        current_tick=10,
    )
    assert all(not r.drift_codes for r in out.reports)
    assert out.summary == "全员稳定"
