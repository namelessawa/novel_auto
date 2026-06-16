"""Phase 5-A unit tests — narrator SYSTEM prompt prefix-cache stability.

Why these tests exist:

* Before iter (Phase 5-A) ``_build_system_prompt`` appended dynamic
  ``style_anchors`` to the SYSTEM message. That broke DeepSeek / ARK
  auto-prefix cache because the SYSTEM string was different on every tick.
* This file pins two invariants:
  1. SYSTEM is bit-identical across ticks regardless of ``style_anchors``.
  2. The anchor information still reaches the LLM — it just moves to the
     head of the USER prompt. Content equivalence preserved.

If a future change re-introduces dynamic content into SYSTEM, test #1 will
fail and the cache regression will be caught at commit time, not after the
$$$ shows up on the bill.
"""

from __future__ import annotations

import json

import pytest

from agents.narrator_agent import NARRATOR_SYSTEM_PROMPT, NarratorAgent
from memory_system.models import Event, StyleAnchor


def _make_event(value: int = 10) -> Event:
    return Event(
        id="evt_phase5a",
        type="exogenous",
        tick=1,
        description="测试事件 — Phase 5-A cache stability",
        narrative_value=value,
        narrative_value_hint=value,
    )


def _narrate_response_json() -> str:
    return json.dumps(
        {
            "narrative_text": "短叙述文本 用于 Phase 5-A 测试。",
            "viewpoint_characters": ["c1"],
            "scene_focus": "test scene",
            "events_consumed": ["evt_phase5a"],
            "open_loops_referenced": [],
            "newly_opened_loops": [],
            "style_diagnostics": {},
            "consistency_flags": [],
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_system_prompt_is_bit_identical_across_anchors(mock_llm) -> None:
    """SYSTEM must be bit-identical across ticks for prefix cache to hit."""
    agent = NarratorAgent(enable_critic=False)
    ev = _make_event()

    anchors_a: list[StyleAnchor] = []
    anchors_b = [
        StyleAnchor(excerpt="风停在城墙之外 灯笼摇了摇", scene_type="atmospheric", weight=1.5),
        StyleAnchor(excerpt="刀光一闪 血溅三尺", scene_type="action", weight=1.0),
    ]
    anchors_c = [
        StyleAnchor(excerpt="完全不同的语感参考 占位文字", scene_type="dialogue", weight=2.0),
    ]

    mock_llm.set_responses(
        [_narrate_response_json(), _narrate_response_json(), _narrate_response_json()]
    )

    for tick_no, anchors in enumerate([anchors_a, anchors_b, anchors_c], start=1):
        await agent.narrate(
            tick=tick_no,
            world_time=tick_no,
            tracking_character_id="c1",
            tick_events=[ev],
            char_states=[],
            recent_chapter_summaries=[],
            open_loops=[],
            style_anchors=anchors,
            last_narration_tick=0,
        )

    systems = [call[0] for call in mock_llm.calls]
    assert len(systems) == 3, f"expected 3 narrate calls, got {len(systems)}"

    # Invariant 1: all SYSTEM prompts are byte-identical.
    assert systems[0] == systems[1] == systems[2], (
        "SYSTEM prompt drifted between ticks — prefix cache will MISS. "
        "Likely cause: someone re-introduced dynamic content into "
        "_build_system_prompt."
    )

    # Invariant 2: SYSTEM equals the pure static template (no dynamic suffix).
    assert systems[0] == NARRATOR_SYSTEM_PROMPT, (
        "SYSTEM diverged from NARRATOR_SYSTEM_PROMPT — there is hidden "
        "templating somewhere in _build_system_prompt."
    )

    # Invariant 3: SYSTEM does NOT contain anchor markers
    # (those must now live in USER head).
    assert "【语感示例" not in systems[0]
    assert "语感参考(只看句长" not in systems[0]


@pytest.mark.asyncio
async def test_user_prompt_carries_anchor_content(mock_llm) -> None:
    """Content equivalence: anchor text moves SYSTEM tail → USER head."""
    agent = NarratorAgent(enable_critic=False)
    ev = _make_event()

    anchor_excerpt_marker = "PHASE5A_UNIQUE_ANCHOR_MARKER_风停在城墙之外"
    anchors = [
        StyleAnchor(
            excerpt=anchor_excerpt_marker, scene_type="atmospheric", weight=1.0
        )
    ]

    mock_llm.set_responses([_narrate_response_json()])
    await agent.narrate(
        tick=1,
        world_time=1,
        tracking_character_id="c1",
        tick_events=[ev],
        char_states=[],
        recent_chapter_summaries=[],
        open_loops=[],
        style_anchors=anchors,
        last_narration_tick=0,
    )

    assert len(mock_llm.calls) == 1
    system_prompt, user_prompt = mock_llm.calls[0]

    # Anchor content MUST appear in USER (so the LLM still sees the style cue).
    assert anchor_excerpt_marker in user_prompt, (
        "Anchor excerpt did not reach USER prompt — Phase 5-A regression: "
        "the style cue got dropped, narrator will lose style anchoring."
    )
    assert "【语感示例 - atmospheric】" in user_prompt
    assert "# 语感参考(只看句长" in user_prompt

    # And MUST NOT appear in SYSTEM (the whole point of the rearrangement).
    assert anchor_excerpt_marker not in system_prompt
    assert "【语感示例" not in system_prompt

    # User prompt should put the anchor block AT THE HEAD (before "# 连载进度").
    head_idx = user_prompt.find("# 语感参考")
    body_idx = user_prompt.find("# 连载进度")
    assert head_idx >= 0 and body_idx > head_idx, (
        "Anchor block should precede '# 连载进度' header in USER prompt."
    )


@pytest.mark.asyncio
async def test_empty_anchors_yields_no_anchor_block_in_user(mock_llm) -> None:
    """Empty style_anchors → no anchor markup in user prompt (no leading blank chunk)."""
    agent = NarratorAgent(enable_critic=False)
    ev = _make_event()

    mock_llm.set_responses([_narrate_response_json()])
    await agent.narrate(
        tick=1,
        world_time=1,
        tracking_character_id="c1",
        tick_events=[ev],
        char_states=[],
        recent_chapter_summaries=[],
        open_loops=[],
        style_anchors=[],
        last_narration_tick=0,
    )

    _, user_prompt = mock_llm.calls[0]
    assert "# 语感参考" not in user_prompt
    assert "【语感示例" not in user_prompt
    # USER prompt should start with "# 连载进度" header, no preceding empty lines.
    assert user_prompt.lstrip().startswith("# 连载进度")
