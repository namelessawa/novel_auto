"""硬状态转移端到端验证 (v2.16)。

CharacterAction 新增 new_location / inventory_added / inventory_removed /
status_added / status_removed / relationship_deltas 字段。本测试验证
Orchestrator._apply_actions 把这些字段正确写回 CharacterState, 并同步
WorldState.locations[].present_characters。

这些转移如果没有落到结构化字段, 长期就会让 Narrator 与 KnowledgeGraph 失同步:
角色 "去了安全屋" 但 location 仍是 loc_1, 一两 tick 内 Narrator 还能圆,
50 tick 后必然爆 consistency_flag。
"""

from __future__ import annotations

import asyncio

import pytest

from agents.orchestrator import Orchestrator
from memory.tick_state import TickState
from memory_system.models import (
    CharacterAction,
    CharacterProfile,
    CharacterState,
    Relationship,
    RelationshipDelta,
    TickLocation,
    WorldState,
)
from nf_core.action_resolver import ActionResolver


def _make_state(tmp_path) -> TickState:
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(
        WorldState(
            world_time=0,
            locations=[
                TickLocation(id="loc_city", name="新城", type="city"),
                TickLocation(id="loc_safehouse", name="安全屋", type="hideout"),
                TickLocation(id="loc_forest", name="北林", type="wilderness"),
            ],
        )
    )
    ts.upsert_character_profile(
        CharacterProfile(
            id="elara", name="Elara", role="主角", importance_tier="A"
        )
    )
    ts.upsert_character_profile(
        CharacterProfile(
            id="zoe", name="Zoe", role="配角", importance_tier="B"
        )
    )
    ts.upsert_character_state(
        CharacterState(
            character_id="elara",
            current_location="loc_city",
            emotional_state="neutral",
            inventory=["旧通讯器"],
            status_effects=[],
            relationships={
                "zoe": Relationship(
                    with_character_id="zoe",
                    type="陌生人",
                    trust=0,
                    history_summary="尚未会面",
                )
            },
        )
    )
    ts.upsert_character_state(
        CharacterState(
            character_id="zoe",
            current_location="loc_city",
        )
    )
    return ts


def _make_orchestrator(ts: TickState) -> Orchestrator:
    """构造一个 Orchestrator, 用 None 占位 agents — 本测试不调用 LLM 阶段。"""
    return Orchestrator(
        tick_state=ts,
        world_simulator=None,  # type: ignore[arg-type]
        character_agents={},
        narrator=None,  # type: ignore[arg-type]
        action_resolver=ActionResolver(),
    )


def test_apply_actions_updates_location_inventory_status(tmp_path):
    ts = _make_state(tmp_path)
    orch = _make_orchestrator(ts)
    action = CharacterAction(
        character_id="elara",
        action_type="move",
        target="loc_safehouse",
        description="爱拉拉沿通风管潜入安全屋",
        new_location="loc_safehouse",
        inventory_added=["撬棍"],
        inventory_removed=["旧通讯器"],
        status_added=["疲惫"],
    )

    events = orch._apply_actions(tick=1, actions=[action])

    new_state = ts.get_character_state("elara")
    assert new_state is not None
    assert new_state.current_location == "loc_safehouse"
    assert "撬棍" in new_state.inventory
    assert "旧通讯器" not in new_state.inventory
    assert "疲惫" in new_state.status_effects

    # 同步刷新 WorldState.locations[].present_characters
    locations_by_id = {loc.id: loc for loc in ts.world_state.locations}
    assert "elara" in locations_by_id["loc_safehouse"].present_characters
    assert "elara" not in locations_by_id["loc_city"].present_characters

    # 应生成 1 个 character_action Event, location 已是新位置
    assert len(events) == 1
    assert events[0].location == "loc_safehouse"
    # nv_hint 应高一些 — 有 location 变化加成
    assert events[0].narrative_value_hint and events[0].narrative_value_hint >= 2


def test_apply_actions_ignores_unknown_location(tmp_path):
    """new_location 不在 WorldState.locations 时不应改 state, 但要打 flag。"""
    ts = _make_state(tmp_path)
    orch = _make_orchestrator(ts)
    action = CharacterAction(
        character_id="elara",
        action_type="move",
        target="ghost_room",
        description="试图前往不存在的地点",
        new_location="loc_ghost",  # 不在 world_state.locations
    )

    events = orch._apply_actions(tick=1, actions=[action])

    new_state = ts.get_character_state("elara")
    assert new_state is not None
    # 位置未变
    assert new_state.current_location == "loc_city"
    # Event.consequences 应记录 unknown_location flag
    assert events[0].consequences == ["unknown_location:loc_ghost"]


def test_apply_actions_merges_relationship_delta(tmp_path):
    ts = _make_state(tmp_path)
    orch = _make_orchestrator(ts)
    action = CharacterAction(
        character_id="elara",
        action_type="speak",
        target="zoe",
        description="坦白父亲十年前的死因",
        relationship_deltas={
            "zoe": RelationshipDelta(
                trust_delta=3,
                new_type="盟友",
                history_entry="t1 坦白",
            )
        },
    )

    orch._apply_actions(tick=1, actions=[action])

    new_state = ts.get_character_state("elara")
    assert new_state is not None
    rel = new_state.relationships["zoe"]
    assert rel.type == "盟友"
    assert rel.trust == 3
    assert "t1 坦白" in rel.history_summary
    assert rel.last_interaction_tick == 1


def test_apply_actions_clamps_trust_within_range(tmp_path):
    """单次大幅信任增量也必须 clamp 到 [-10, 10]。"""
    ts = _make_state(tmp_path)
    orch = _make_orchestrator(ts)
    # 现有 trust=0 + delta=15 → 应 clamp 到 10
    action = CharacterAction(
        character_id="elara",
        action_type="bond",
        target="zoe",
        relationship_deltas={
            "zoe": RelationshipDelta(trust_delta=15),
        },
    )

    orch._apply_actions(tick=1, actions=[action])

    new_state = ts.get_character_state("elara")
    assert new_state is not None
    assert new_state.relationships["zoe"].trust == 10


def test_apply_actions_no_location_change_skips_sync(tmp_path):
    """无 location 变化时不应触发 _sync_location_membership (此处仅验证不抛错)。"""
    ts = _make_state(tmp_path)
    orch = _make_orchestrator(ts)
    action = CharacterAction(
        character_id="elara",
        action_type="wait",
        description="在原地凝视通讯器",
        status_added=["焦虑"],
    )

    orch._apply_actions(tick=1, actions=[action])

    new_state = ts.get_character_state("elara")
    assert new_state is not None
    assert new_state.current_location == "loc_city"
    assert "焦虑" in new_state.status_effects
