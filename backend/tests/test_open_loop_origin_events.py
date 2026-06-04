"""OpenLoop.origin_event_ids 字段 + Narrator 解析 (v2.21)。

回归 P2:此前 OpenLoop 模型未声明 origin_event_ids, _TickModelConfig.extra=
"ignore" 把 LLM 给出的字段悄悄吃掉, orchestrator 的 mark_protected 分支
永远是 [] → 伏笔源事件不会被保护, MemoryCompressor 可压缩。

测试覆盖:
1. OpenLoop 直接 model_validate 接受 origin_event_ids
2. NarratorAgent._parse_output 把 LLM JSON 里的 origin_event_ids 透传到
   OpenLoop 实例 — 这是字段进入 orchestrator 的唯一通路
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from memory_system.models import OpenLoop


def test_open_loop_accepts_origin_event_ids():
    loop = OpenLoop(
        id="loop_1",
        opened_tick=10,
        description="主角的真实身份",
        origin_event_ids=["evt_5", "evt_7"],
    )
    assert loop.origin_event_ids == ["evt_5", "evt_7"]


def test_open_loop_defaults_origin_event_ids_to_empty():
    """老数据 / LLM 未填字段 → 兼容降级为 []"""
    loop = OpenLoop(id="loop_2", opened_tick=10, description="x")
    assert loop.origin_event_ids == []


def test_open_loop_origin_event_ids_dumps_in_json():
    """save → load round-trip 不丢字段, 否则 mark_protected 的 reason
    路径(open_loop:id)就失去线索。"""
    loop = OpenLoop(
        id="loop_3",
        opened_tick=10,
        description="x",
        origin_event_ids=["evt_a"],
    )
    payload = loop.model_dump_json()
    restored = OpenLoop.model_validate_json(payload)
    assert restored.origin_event_ids == ["evt_a"]


def test_narrator_parse_preserves_origin_event_ids():
    """LLM 输出在 newly_opened_loops 里给 origin_event_ids, 解析后保留。

    复刻 orchestrator 的真实消费路径:它对 narrator_out.newly_opened_loops
    每条 loop 调 getattr(loop, "origin_event_ids", None) 然后 mark_protected。
    """
    from agents.narrator_agent import NarratorAgent

    agent = NarratorAgent()
    raw = json.dumps(
        {
            "narrative_text": "深夜,他翻开父亲留下的信。",
            "estimated_length": "short",
            "viewpoint_characters": ["diana"],
            "scene_focus": "线索揭示",
            "events_consumed": ["evt_5"],
            "open_loops_referenced": [],
            "newly_opened_loops": [
                {
                    "description": "父亲信中提及的'第三方'",
                    "involved_characters": ["diana"],
                    "type": "mystery",
                    "urgency": 7,
                    "origin_event_ids": ["evt_5"],
                }
            ],
            "style_diagnostics": {},
            "consistency_flags": [],
        },
        ensure_ascii=False,
    )

    out = agent._parse_output(raw, estimated_length="short", tick=12, tick_events=[])
    assert len(out.newly_opened_loops) == 1
    loop = out.newly_opened_loops[0]
    assert loop.origin_event_ids == ["evt_5"]
    # 验证 getattr 路径 — 即 orchestrator 的真实读法
    assert getattr(loop, "origin_event_ids", None) == ["evt_5"]
