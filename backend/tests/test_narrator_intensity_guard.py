"""Phase 6 iter#M — Narrator 高 intensity 段落上限护栏.

接 verdict-spike-rootcause-0625 的 carry-forward #1. Run 1 (24 日 bench)
narrator 在 t201 进入 100% all-narrate + 长段落 stuck-state 直到 quota wall.
Run 2 (25 日) 同样在 t201 spike 但 t251 主动 recover. 差别是 LLM
stochasticity.

本 iter 加硬约束: 跟踪最近 10 tick 的 narrative chars, 当 ≥5 tick > 1500 字,
下 tick prompt 加 "请短促收尾或留白" directive, 不阻 spike (允许真正 climax)
但阻 sustained-climax.

锁定:
* 空 history → guard 不激活
* < 阈值 count → guard 不激活
* ≥ 阈值 count → guard 激活
* guard 激活时 prompt 含 directive
* guard 未激活时 prompt 不含 directive
* env NARRATOR_INTENSITY_GUARD_ENABLE=0 → 永不激活
* env NARRATOR_INTENSITY_GUARD_CHARS 自定义
* env NARRATOR_INTENSITY_GUARD_COUNT 自定义
* 记录的 chars 队列 cap = 10 (最早的被挤掉)
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = Path(__file__).resolve().parents[1]
for p in (_ROOT, _BACKEND):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import pytest

from agents.narrator_agent import NarratorAgent


# ---------------------------------------------------------------------------
# Guard activation logic
# ---------------------------------------------------------------------------


def test_guard_empty_history_inactive() -> None:
    n = NarratorAgent()
    assert n._intensity_guard_active() is False


def test_guard_below_count_threshold_inactive() -> None:
    """4 of 10 narratives over 1500 chars → 不激活 (默认 count=5)."""
    n = NarratorAgent()
    for chars in [1800, 1900, 1700, 1600, 800, 700, 500, 400, 300, 200]:
        n._record_narrative_chars(chars)
    assert n._intensity_guard_active() is False


def test_guard_at_count_threshold_active() -> None:
    """5 of 10 > 1500 → 激活."""
    n = NarratorAgent()
    for chars in [1800, 1900, 1700, 1600, 1550, 700, 500, 400, 300, 200]:
        n._record_narrative_chars(chars)
    assert n._intensity_guard_active() is True


def test_guard_all_long_active() -> None:
    n = NarratorAgent()
    for chars in [2000] * 10:
        n._record_narrative_chars(chars)
    assert n._intensity_guard_active() is True


# ---------------------------------------------------------------------------
# Sliding window — old narratives drop out
# ---------------------------------------------------------------------------


def test_guard_history_window_caps_at_10() -> None:
    """记录 15 条, 仅最近 10 条参与判定."""
    n = NarratorAgent()
    # 头 5 条都长 (would trigger if kept) + 后 10 条都短
    for chars in [2000] * 5 + [300] * 10:
        n._record_narrative_chars(chars)
    # 队列里只有后 10 条 (全 300) → 不激活
    assert n._intensity_guard_active() is False


# ---------------------------------------------------------------------------
# Env knobs
# ---------------------------------------------------------------------------


def test_guard_disabled_via_env(monkeypatch) -> None:
    monkeypatch.setenv("NARRATOR_INTENSITY_GUARD_ENABLE", "0")
    n = NarratorAgent()
    for chars in [2000] * 10:
        n._record_narrative_chars(chars)
    assert n._intensity_guard_active() is False


def test_guard_custom_chars_threshold(monkeypatch) -> None:
    """CHARS=1000 + 5 个 > 1000 → 激活, 即使默认 1500 下不激活."""
    monkeypatch.setenv("NARRATOR_INTENSITY_GUARD_CHARS", "1000")
    monkeypatch.delenv("NARRATOR_INTENSITY_GUARD_ENABLE", raising=False)
    n = NarratorAgent()
    for chars in [1200, 1100, 1050, 1300, 1400, 500, 400, 300, 200, 100]:
        n._record_narrative_chars(chars)
    assert n._intensity_guard_active() is True


def test_guard_custom_count_threshold(monkeypatch) -> None:
    """COUNT=3 + 3 个 > 1500 → 激活."""
    monkeypatch.setenv("NARRATOR_INTENSITY_GUARD_COUNT", "3")
    monkeypatch.delenv("NARRATOR_INTENSITY_GUARD_ENABLE", raising=False)
    n = NarratorAgent()
    for chars in [1800, 1700, 1900, 500, 400, 300, 200, 100, 0, 0]:
        n._record_narrative_chars(chars)
    assert n._intensity_guard_active() is True


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------


_GUARD_PHRASE = "已连续高密度叙事"


def test_guard_directive_appears_when_active() -> None:
    n = NarratorAgent()
    for chars in [2000] * 10:
        n._record_narrative_chars(chars)
    assert n._intensity_guard_active() is True
    block = n._render_intensity_guard_block()
    assert _GUARD_PHRASE in block


def test_guard_directive_empty_when_inactive() -> None:
    n = NarratorAgent()
    block = n._render_intensity_guard_block()
    assert block == ""


def test_guard_directive_empty_when_env_disabled(monkeypatch) -> None:
    monkeypatch.setenv("NARRATOR_INTENSITY_GUARD_ENABLE", "0")
    n = NarratorAgent()
    for chars in [2000] * 10:
        n._record_narrative_chars(chars)
    assert n._render_intensity_guard_block() == ""


# ---------------------------------------------------------------------------
# Integration with _build_user_prompt
# ---------------------------------------------------------------------------


def test_guard_phrase_in_user_prompt_when_active() -> None:
    """完整 _build_user_prompt 包含 guard directive when active."""
    n = NarratorAgent()
    for chars in [2000] * 10:
        n._record_narrative_chars(chars)
    prompt = n._build_user_prompt(
        tick=1,
        world_time=100,
        tracking_character_id="char_a",
        tick_events=[],
        char_states=[],
        recent_chapter_summaries=[],
        open_loops=[],
        target_chars="short",
        novel_title="test",
    )
    assert _GUARD_PHRASE in prompt


def test_guard_phrase_not_in_user_prompt_when_inactive() -> None:
    n = NarratorAgent()
    prompt = n._build_user_prompt(
        tick=1,
        world_time=100,
        tracking_character_id="char_a",
        tick_events=[],
        char_states=[],
        recent_chapter_summaries=[],
        open_loops=[],
        target_chars="short",
        novel_title="test",
    )
    assert _GUARD_PHRASE not in prompt
