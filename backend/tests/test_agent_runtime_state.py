"""AgentRuntimeState — agent 运行态(失败计数 / 冷却 / 模型层级覆写)。

v2.18 — agent 运行态从"实例属性"提升到"持久化外部状态", 让 CharacterAgent
重建后仍能记得自己最近 N tick 失败了几次。
"""

from __future__ import annotations

from memory.tick_state import TickState
from memory_system.models import AgentRuntimeState


def test_agent_runtime_state_default_values() -> None:
    rs = AgentRuntimeState(agent_id="character_agent:elara")
    assert rs.agent_id == "character_agent:elara"
    assert rs.last_invoked_tick == 0
    assert rs.failure_count == 0
    assert rs.cooldown_until_tick == 0
    assert rs.model_tier_override == ""


def test_tick_state_upsert_and_get_runtime_state(tmp_path) -> None:
    ts = TickState(data_dir=str(tmp_path))
    rs = AgentRuntimeState(
        agent_id="character_agent:elara",
        last_invoked_tick=5,
        failure_count=2,
    )
    ts.upsert_agent_runtime_state(rs)
    got = ts.get_agent_runtime_state("character_agent:elara")
    assert got is not None
    assert got.failure_count == 2
    assert got.last_invoked_tick == 5


def test_tick_state_get_runtime_state_missing(tmp_path) -> None:
    ts = TickState(data_dir=str(tmp_path))
    assert ts.get_agent_runtime_state("unknown") is None


def test_record_agent_invocation_success_resets_failure(tmp_path) -> None:
    """成功调用后, 失败计数应清零, last_invoked_tick 推进。"""
    ts = TickState(data_dir=str(tmp_path))
    ts.upsert_agent_runtime_state(
        AgentRuntimeState(agent_id="x", failure_count=3, last_invoked_tick=1)
    )
    ts.record_agent_invocation("x", tick=10, success=True)
    got = ts.get_agent_runtime_state("x")
    assert got is not None
    assert got.last_invoked_tick == 10
    assert got.failure_count == 0


def test_record_agent_invocation_failure_increments(tmp_path) -> None:
    """失败累计, 达到阈值后设置 cooldown_until_tick = tick + 5。"""
    ts = TickState(data_dir=str(tmp_path))
    # 起点: 已失败 2 次
    ts.upsert_agent_runtime_state(
        AgentRuntimeState(agent_id="x", failure_count=2)
    )
    ts.record_agent_invocation("x", tick=10, success=False)
    got = ts.get_agent_runtime_state("x")
    assert got is not None
    assert got.failure_count == 3
    # 阈值 = 3 → 触发 cooldown
    assert got.cooldown_until_tick == 15


def test_agent_runtime_state_persistence_roundtrip(tmp_path) -> None:
    """save/load 后 runtime states 完整还原。"""
    ts = TickState(data_dir=str(tmp_path))
    ts.upsert_agent_runtime_state(
        AgentRuntimeState(
            agent_id="character_agent:elara",
            last_invoked_tick=42,
            failure_count=1,
            cooldown_until_tick=47,
            model_tier_override="haiku",
        )
    )
    ts.save()

    ts2 = TickState(data_dir=str(tmp_path))
    assert ts2.load() is True
    got = ts2.get_agent_runtime_state("character_agent:elara")
    assert got is not None
    assert got.last_invoked_tick == 42
    assert got.failure_count == 1
    assert got.cooldown_until_tick == 47
    assert got.model_tier_override == "haiku"


def test_is_agent_in_cooldown(tmp_path) -> None:
    """is_agent_in_cooldown 在 cooldown 窗口内返回 True。"""
    ts = TickState(data_dir=str(tmp_path))
    ts.upsert_agent_runtime_state(
        AgentRuntimeState(agent_id="x", cooldown_until_tick=20)
    )
    assert ts.is_agent_in_cooldown("x", current_tick=15) is True
    assert ts.is_agent_in_cooldown("x", current_tick=20) is True
    assert ts.is_agent_in_cooldown("x", current_tick=21) is False
    # 未知 agent 视为不在冷却
    assert ts.is_agent_in_cooldown("unknown", current_tick=15) is False
