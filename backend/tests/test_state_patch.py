"""StatePatch — 通用状态补丁层 (v2.18)。

设计意图: EventInjector 想"爆炸波及房间所有人增加'受伤'状态"或者
ConsistencyGuardian 想修正"角色 A 的 location 应该是 X"时, 不应再借道
CharacterAction (那是角色意志的输出, 这两类是外部权威)。

StateOp 是单字段操作 (field/op/value), StatePatch 携带 source_agent /
target_type / target_id / ops + 可选 confidence 与 reason。

Orchestrator._apply_state_patches 应用补丁, 优先级与 CharacterAction 的硬
状态转移并列, 不替代。
"""

from __future__ import annotations

import pytest

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


def _make_state(tmp_path) -> TickState:
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(
        WorldState(
            world_time=0,
            locations=[
                TickLocation(id="loc_city", name="新城", type="city"),
                TickLocation(id="loc_safehouse", name="安全屋", type="hideout"),
            ],
        )
    )
    ts.upsert_character_profile(
        CharacterProfile(id="elara", name="Elara", role="主角", importance_tier="A")
    )
    ts.upsert_character_state(
        CharacterState(
            character_id="elara",
            current_location="loc_city",
            money=100,
            inventory=["旧通讯器"],
            status_effects=["疲惫"],
        )
    )
    return ts


def _orch(ts: TickState) -> Orchestrator:
    return Orchestrator(
        tick_state=ts,
        world_simulator=None,  # type: ignore[arg-type]
        character_agents={},
        narrator=None,  # type: ignore[arg-type]
        action_resolver=ActionResolver(),
    )


# ------------------------------------------------------------------
# 模型本身
# ------------------------------------------------------------------


def test_state_op_basic_fields() -> None:
    op = StateOp(field="money", op="add", value=50)
    assert op.field == "money"
    assert op.op == "add"
    assert op.value == 50


def test_state_op_rejects_unknown_op() -> None:
    with pytest.raises(Exception):
        StateOp(field="money", op="multiply", value=2)


def test_state_patch_basic_assembly() -> None:
    patch = StatePatch(
        source_agent="event_injector",
        target_type="character",
        target_id="elara",
        ops=[StateOp(field="status_effects", op="append", value="受伤")],
        confidence=0.8,
        reason="爆炸波及房间",
    )
    assert patch.source_agent == "event_injector"
    assert patch.target_type == "character"
    assert patch.target_id == "elara"
    assert patch.confidence == 0.8
    assert len(patch.ops) == 1


# ------------------------------------------------------------------
# Orchestrator._apply_state_patches — character target
# ------------------------------------------------------------------


def test_apply_patch_set_money(tmp_path) -> None:
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    patch = StatePatch(
        source_agent="event_injector",
        target_type="character",
        target_id="elara",
        ops=[StateOp(field="money", op="set", value=42)],
    )
    diag = orch._apply_state_patches(tick=1, patches=[patch])
    assert diag.applied == 1
    assert diag.rejected == 0
    assert ts.get_character_state("elara").money == 42


def test_apply_patch_add_money(tmp_path) -> None:
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    patch = StatePatch(
        source_agent="event_injector",
        target_type="character",
        target_id="elara",
        ops=[StateOp(field="money", op="add", value=30)],
    )
    orch._apply_state_patches(tick=1, patches=[patch])
    assert ts.get_character_state("elara").money == 130


def test_apply_patch_append_status_effect(tmp_path) -> None:
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    patch = StatePatch(
        source_agent="event_injector",
        target_type="character",
        target_id="elara",
        ops=[StateOp(field="status_effects", op="append", value="受伤")],
        reason="爆炸波及房间",
    )
    orch._apply_state_patches(tick=1, patches=[patch])
    st = ts.get_character_state("elara")
    assert "受伤" in st.status_effects
    assert "疲惫" in st.status_effects  # 原有不应丢


def test_apply_patch_remove_inventory(tmp_path) -> None:
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    patch = StatePatch(
        source_agent="consistency_guardian",
        target_type="character",
        target_id="elara",
        ops=[StateOp(field="inventory", op="remove", value="旧通讯器")],
        reason="此前误录入, 角色实际从未持有",
    )
    orch._apply_state_patches(tick=1, patches=[patch])
    assert "旧通讯器" not in ts.get_character_state("elara").inventory


def test_apply_patch_set_location_validates(tmp_path) -> None:
    """目标 location 必须存在于 WorldState.locations 才接受, 否则 rejected。"""
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    bad = StatePatch(
        source_agent="event_injector",
        target_type="character",
        target_id="elara",
        ops=[StateOp(field="current_location", op="set", value="loc_ghost")],
    )
    diag = orch._apply_state_patches(tick=1, patches=[bad])
    assert diag.rejected == 1
    # 位置未变
    assert ts.get_character_state("elara").current_location == "loc_city"


def test_apply_patch_unknown_character_rejected(tmp_path) -> None:
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    patch = StatePatch(
        source_agent="event_injector",
        target_type="character",
        target_id="ghost",
        ops=[StateOp(field="money", op="set", value=10)],
    )
    diag = orch._apply_state_patches(tick=1, patches=[patch])
    assert diag.applied == 0
    assert diag.rejected == 1


def test_apply_patch_money_clamps_to_zero(tmp_path) -> None:
    """money set 为负数 → clamp 到 0, 但仍记 applied 并报 flag。"""
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    patch = StatePatch(
        source_agent="event_injector",
        target_type="character",
        target_id="elara",
        ops=[StateOp(field="money", op="add", value=-500)],
    )
    diag = orch._apply_state_patches(tick=1, patches=[patch])
    assert diag.applied == 1
    assert ts.get_character_state("elara").money == 0
    assert "money_overdraft" in diag.flags


# ------------------------------------------------------------------
# Orchestrator._apply_state_patches — world target
# ------------------------------------------------------------------


def test_apply_patch_set_world_weather(tmp_path) -> None:
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    patch = StatePatch(
        source_agent="world_simulator",
        target_type="world",
        target_id="",
        ops=[StateOp(field="weather", op="set", value="暴雪")],
    )
    diag = orch._apply_state_patches(tick=1, patches=[patch])
    assert diag.applied == 1
    assert ts.world_state.weather == "暴雪"


def test_apply_patch_append_world_rule(tmp_path) -> None:
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    patch = StatePatch(
        source_agent="event_injector",
        target_type="world",
        target_id="",
        ops=[StateOp(field="active_global_events", op="append", value="瘟疫")],
    )
    orch._apply_state_patches(tick=1, patches=[patch])
    assert "瘟疫" in ts.world_state.active_global_events


def test_unsupported_target_type_rejected(tmp_path) -> None:
    """faction / location 目标类型本阶段不支持, 应 rejected 而非崩溃。"""
    ts = _make_state(tmp_path)
    orch = _orch(ts)
    patch = StatePatch(
        source_agent="event_injector",
        target_type="faction",
        target_id="house_lannister",
        ops=[StateOp(field="leader_character_id", op="set", value="tyrion")],
    )
    diag = orch._apply_state_patches(tick=1, patches=[patch])
    assert diag.applied == 0
    assert diag.rejected == 1
