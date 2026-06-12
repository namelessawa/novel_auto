"""iter#103 — Showrunner loops_to_close 字段解析 + orchestrator wire.

Phase 2 §closed=0 leakage 修复: 跨 130 tick × 3 seed bench 里 close_open_loop
从未被自动调用, 加 Showrunner 显式 close 决策.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.showrunner import Showrunner, ShowrunnerOutput


# --------------------------------------------------------------------- parse


def _make_payload(loops_to_close_value):
    return json.dumps(
        {
            "pacing_assessment": {"current_intensity": "high", "recent_trend": "rising",
                                  "diagnosis": "测试"},
            "conflict_pool_status": {"count": 8, "health": "low"},
            "cold_threads": [],
            "arc_status": [],
            "recommendations": [],
            "loops_to_close": loops_to_close_value,
        },
        ensure_ascii=False,
    )


def test_parse_loops_to_close_str_list():
    sr = Showrunner()
    out = sr._parse_output(_make_payload(["loop_3", "loop_7"]))
    assert out.loops_to_close == ["loop_3", "loop_7"]


def test_parse_loops_to_close_dict_objects():
    """LLM 偶尔会返回 [{"loop_id": "loop_3"}, ...] 而非纯 str list."""
    sr = Showrunner()
    out = sr._parse_output(_make_payload([{"loop_id": "loop_3"}, {"id": "loop_7"}]))
    assert out.loops_to_close == ["loop_3", "loop_7"]


def test_parse_loops_to_close_empty():
    sr = Showrunner()
    out = sr._parse_output(_make_payload([]))
    assert out.loops_to_close == []


def test_parse_loops_to_close_missing_field():
    """老 prompt 不输出此字段 → 解析必须默认 []."""
    sr = Showrunner()
    out = sr._parse_output(
        json.dumps(
            {
                "pacing_assessment": {},
                "conflict_pool_status": {"count": 0, "health": "ok"},
                "recommendations": [],
            }
        )
    )
    assert out.loops_to_close == []


def test_parse_loops_to_close_skips_invalid_entries():
    sr = Showrunner()
    out = sr._parse_output(_make_payload(["loop_a", "", None, 42, "loop_b"]))
    assert out.loops_to_close == ["loop_a", "loop_b"]


def test_parse_loops_to_close_strips_whitespace():
    sr = Showrunner()
    out = sr._parse_output(_make_payload(["  loop_x  ", "\tloop_y\n"]))
    assert out.loops_to_close == ["loop_x", "loop_y"]


# ------------------------------------------------------------- prompt content


def test_system_prompt_documents_close_criteria():
    """system prompt 必须明确 close 决策准则 (iter#103)."""
    from agents.showrunner import SYSTEM_PROMPT

    assert "loops_to_close" in SYSTEM_PROMPT
    # 6 是默认 cap, prompt 用 "≥ 6" 标明触发阈值
    assert "≥ 6" in SYSTEM_PROMPT or "open_loops" in SYSTEM_PROMPT
    # 优先 stale 最远 / urgency=low 的关闭原则
    assert "stale" in SYSTEM_PROMPT


def test_system_prompt_covers_4_to_5_zone():
    """iter#106 review HIGH-2: [4, 5] 区间必须显式标明 (避免死区)."""
    from agents.showrunner import SYSTEM_PROMPT

    # 必须覆盖 ≥6 / [4,5] / <4 三档
    assert "[4, 5]" in SYSTEM_PROMPT or "4 到 5" in SYSTEM_PROMPT
    assert "< 4" in SYSTEM_PROMPT
