"""Phase 2 Stage 4 (iter#93 review fix) — prompt-contract tests for
event_injector._build_prompt.

确保 iter#90 加入的 stale_loops / stale_ticks 字段真在 user_prompt 里出现.
没有这些 token, SYSTEM_PROMPT 原则 #6/#7 变成死指令, Stage 3 长程修复
被静默拆除.
"""

from __future__ import annotations

from agents.event_injector import EventInjector
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    OpenLoop,
    TickLocation,
    WorldState,
)


def _make_injector_with_loops() -> tuple[EventInjector, list]:
    """构造一个 injector + 3 个 open_loops, 其中 2 个 stale."""
    inj = EventInjector()
    open_loops = [
        OpenLoop(
            id="l_fresh",
            opened_tick=18,
            description="新近开启的伏笔",
            urgency=5,
            type="mystery",
            last_referenced_tick=18,
        ),
        OpenLoop(
            id="l_stale1",
            opened_tick=0,
            description="20+ tick 未推进的旧伏笔 #1",
            urgency=4,
            type="conflict",
            last_referenced_tick=0,
        ),
        OpenLoop(
            id="l_stale2",
            opened_tick=2,
            description="20+ tick 未推进的旧伏笔 #2",
            urgency=6,
            type="threat",
            last_referenced_tick=5,
        ),
    ]
    return inj, open_loops


def test_build_prompt_contains_stale_loops_header() -> None:
    """header 必须包含 stale_loops 计数."""
    inj, loops = _make_injector_with_loops()
    prompt = inj._build_prompt(
        tick=30,
        world_state=WorldState(world_time=30),
        recent_events=[],
        tracking_chars=[],
        open_loops=loops,
        showrunner_recs=[],
        dormant_characters=[],
    )
    assert "stale_loops" in prompt, "header 必须有 stale_loops 字段"


def test_build_prompt_contains_stale_ticks_per_loop() -> None:
    """每条 open_loop 必须含 stale_ticks 字段."""
    inj, loops = _make_injector_with_loops()
    prompt = inj._build_prompt(
        tick=30,
        world_state=WorldState(world_time=30),
        recent_events=[],
        tracking_chars=[],
        open_loops=loops,
        showrunner_recs=[],
        dormant_characters=[],
    )
    assert "stale_ticks" in prompt, "open_loop JSON 字段必须有 stale_ticks"


def test_build_prompt_stale_count_matches_expectation() -> None:
    """tick=30 时 l_stale1 (last_ref=0) 与 l_stale2 (last_ref=5) 应判 stale,
    l_fresh (last_ref=8) 不算. 期望 stale_loops=2."""
    inj, loops = _make_injector_with_loops()
    prompt = inj._build_prompt(
        tick=30,
        world_state=WorldState(world_time=30),
        recent_events=[],
        tracking_chars=[],
        open_loops=loops,
        showrunner_recs=[],
        dormant_characters=[],
    )
    assert "stale_loops=2" in prompt, (
        f"期望 stale_loops=2 (tick=30 时 l_fresh last_ref=18 → 12 tick stale 不到 20; "
        f"另两条 last_ref ≤5 → 25-30 tick stale 算 stale), prompt 实际: "
        f"{prompt[:200]!r}"
    )


def test_build_prompt_no_stale_when_all_fresh() -> None:
    """所有 loop 都 fresh → stale_loops=0."""
    inj = EventInjector()
    fresh_loops = [
        OpenLoop(
            id="l1",
            opened_tick=28,
            description="刚开",
            urgency=5,
            type="mystery",
            last_referenced_tick=28,
        ),
    ]
    prompt = inj._build_prompt(
        tick=30,
        world_state=WorldState(world_time=30),
        recent_events=[],
        tracking_chars=[],
        open_loops=fresh_loops,
        showrunner_recs=[],
        dormant_characters=[],
    )
    assert "stale_loops=0" in prompt


# iter#96 — open_pressure 第二信号 (plot 密集题材 stale 升起前就 cap)
# ---------------------------------------------------------------------------


def test_build_prompt_open_pressure_low_below_cap(monkeypatch) -> None:
    monkeypatch.setenv("EVENT_INJECTOR_OPEN_LOOP_CAP", "6")
    inj, loops = _make_injector_with_loops()  # 3 loops < 6
    prompt = inj._build_prompt(
        tick=30,
        world_state=WorldState(world_time=30),
        recent_events=[],
        tracking_chars=[],
        open_loops=loops,
        showrunner_recs=[],
        dormant_characters=[],
    )
    assert "open_pressure=low" in prompt
    assert "cap=6" in prompt


def test_build_prompt_open_pressure_high_at_or_above_cap(monkeypatch) -> None:
    monkeypatch.setenv("EVENT_INJECTOR_OPEN_LOOP_CAP", "3")
    inj, loops = _make_injector_with_loops()  # exactly 3 loops, cap=3
    prompt = inj._build_prompt(
        tick=30,
        world_state=WorldState(world_time=30),
        recent_events=[],
        tracking_chars=[],
        open_loops=loops,
        showrunner_recs=[],
        dormant_characters=[],
    )
    assert "open_pressure=high" in prompt


def test_build_prompt_cap_min_clamped_to_3(monkeypatch) -> None:
    """env 设 1 应被 clamp 到 3, 防止极端配置让 cap 失去意义."""
    monkeypatch.setenv("EVENT_INJECTOR_OPEN_LOOP_CAP", "1")
    inj, loops = _make_injector_with_loops()  # 3 loops
    prompt = inj._build_prompt(
        tick=30,
        world_state=WorldState(world_time=30),
        recent_events=[],
        tracking_chars=[],
        open_loops=loops,
        showrunner_recs=[],
        dormant_characters=[],
    )
    assert "cap=3" in prompt
