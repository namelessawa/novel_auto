"""EventInjector 产 StatePatch (v2.18 Phase 8)。

让 EventInjector 在产 Event 的同时, 可选产 StatePatch — 对于强因果事件
(爆炸波及所有人 / 瘟疫扩散 / 某人当场死亡), LLM 可以提交 StatePatch
让世界状态立即生效, 而不是借道 character_action。

测试:
1. _parse_output 解析 state_patches 字段
2. 无 state_patches 时返回空列表
3. 非法 patch 单条跳过, 其他保留
4. Orchestrator 阶段 5d 自动应用 EventInjectorOutput.state_patches
"""

from __future__ import annotations

import json

import pytest

from agents.event_injector import EventInjector, EventInjectorOutput
from agents.orchestrator import Orchestrator
from memory.tick_state import TickState
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    StateOp,
    StatePatch,
    TickLocation,
    WorldState,
)
from nf_core.action_resolver import ActionResolver


def _ts(tmp_path) -> TickState:
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(
        WorldState(locations=[TickLocation(id="loc_a", name="A")])
    )
    ts.upsert_character_profile(
        CharacterProfile(id="elara", name="Elara", importance_tier="A")
    )
    ts.upsert_character_state(
        CharacterState(character_id="elara", current_location="loc_a", money=100)
    )
    return ts


def _payload_with_patches() -> str:
    return json.dumps(
        {
            "events": [
                {
                    "id": "evt_explosion",
                    "type": "dramatic",
                    "tick": 5,
                    "location": "loc_a",
                    "participants": ["elara"],
                    "description": "弹药库爆炸, 房间内所有人轻伤",
                    "visible_to": ["all_in_location"],
                    "narrative_value": 8,
                    "consequences": [],
                }
            ],
            "state_patches": [
                {
                    "source_agent": "event_injector",
                    "target_type": "character",
                    "target_id": "elara",
                    "ops": [
                        {"field": "status_effects", "op": "append", "value": "受伤"}
                    ],
                    "confidence": 0.9,
                    "reason": "爆炸波及",
                }
            ],
            "no_events_reason": None,
        },
        ensure_ascii=False,
    )


def _payload_no_patches() -> str:
    return json.dumps(
        {
            "events": [
                {
                    "id": "evt_1",
                    "type": "exogenous",
                    "tick": 3,
                    "location": "loc_a",
                    "participants": [],
                    "description": "远方传来钟声",
                    "visible_to": ["all"],
                    "narrative_value": 4,
                    "consequences": [],
                }
            ],
            "no_events_reason": None,
        },
        ensure_ascii=False,
    )


def _payload_mixed_invalid() -> str:
    return json.dumps(
        {
            "events": [],
            "state_patches": [
                {
                    "source_agent": "event_injector",
                    "target_type": "character",
                    "target_id": "elara",
                    "ops": [{"field": "money", "op": "add", "value": 20}],
                },
                {
                    # invalid: target_type 缺失
                    "ops": [{"field": "money", "op": "add", "value": 5}],
                },
                {
                    "source_agent": "event_injector",
                    "target_type": "world",
                    "target_id": "",
                    "ops": [{"field": "weather", "op": "set", "value": "暴雪"}],
                },
            ],
        },
        ensure_ascii=False,
    )


# ------------------------------------------------------------------
# _parse_output 解析
# ------------------------------------------------------------------


def test_parse_output_extracts_state_patches() -> None:
    injector = EventInjector()
    out = injector._parse_output(_payload_with_patches(), tick=5, open_loop_count=3)
    assert isinstance(out, EventInjectorOutput)
    assert len(out.events) == 1
    assert len(out.state_patches) == 1
    assert out.state_patches[0].target_id == "elara"
    assert out.state_patches[0].ops[0].field == "status_effects"


def test_parse_output_without_state_patches() -> None:
    injector = EventInjector()
    out = injector._parse_output(_payload_no_patches(), tick=3, open_loop_count=2)
    assert len(out.events) == 1
    assert out.state_patches == []


def test_parse_output_skips_invalid_patches_keeps_valid() -> None:
    injector = EventInjector()
    out = injector._parse_output(_payload_mixed_invalid(), tick=7, open_loop_count=1)
    # 2 个合法, 1 个无效被丢弃
    assert len(out.state_patches) == 2
    fields = sorted(
        (p.target_type, p.ops[0].field) for p in out.state_patches
    )
    assert fields == [("character", "money"), ("world", "weather")]


# ------------------------------------------------------------------
# Orchestrator 集成 — 阶段 2 注入器返回 patches 时, 阶段 5d 应用
# ------------------------------------------------------------------


class _StubInjector:
    """模拟 EventInjector, 直接返回预备好的 EventInjectorOutput。"""

    def __init__(self, output: EventInjectorOutput) -> None:
        self.output = output

    async def inject(self, **kwargs) -> EventInjectorOutput:
        return self.output


@pytest.mark.asyncio
async def test_orchestrator_consumes_event_injector_state_patches(
    tmp_path,
) -> None:
    """EventInjector 输出 state_patches 时, Orchestrator 应在阶段 5d 应用。"""
    ts = _ts(tmp_path)
    injector_out = EventInjectorOutput(
        events=[],
        state_patches=[
            StatePatch(
                source_agent="event_injector",
                target_type="character",
                target_id="elara",
                ops=[StateOp(field="status_effects", op="append", value="受伤")],
                reason="爆炸",
            ),
            StatePatch(
                source_agent="event_injector",
                target_type="world",
                target_id="",
                ops=[StateOp(field="weather", op="set", value="暴雪")],
            ),
        ],
    )
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=None,  # type: ignore[arg-type]
        character_agents={},
        narrator=None,  # type: ignore[arg-type]
        action_resolver=ActionResolver(),
        event_injector=_StubInjector(injector_out),  # type: ignore[arg-type]
    )
    # 直接调度 apply state patches 路径
    diag = orch._apply_state_patches(
        tick=5, patches=injector_out.state_patches
    )
    assert diag.applied == 2
    assert "受伤" in ts.get_character_state("elara").status_effects
    assert ts.world_state.weather == "暴雪"
