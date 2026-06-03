"""幻觉率观测闭环 (v2.18 Phase 5)。

Guardian → TickState → AgentRuntimeState 计数。
默认 shadow mode (HALLUCINATION_AUTO_DEGRADE 未设): 只统计, 不触发降级。
env flag 开启时: 同时写 model_tier_override='haiku'。

测试三层:
1. AgentRuntimeState 新增字段默认值
2. TickState.record_degrade_recommendation 写入 + clamp
3. TickState.get_hallucination_stats 查询
4. Orchestrator 阶段 7 自动消费 Guardian 输出
5. env flag 切换行为
"""

from __future__ import annotations

import os

import pytest

from agents.consistency_guardian import GuardianConflict, GuardianOutput
from agents.orchestrator import Orchestrator
from memory.tick_state import TickState
from memory_system.models import (
    AgentRuntimeState,
    CharacterProfile,
    CharacterState,
    Event,
    WorldState,
)
from nf_core.action_resolver import ActionResolver


def _ts(tmp_path) -> TickState:
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(WorldState())
    ts.upsert_character_profile(
        CharacterProfile(id="elara", name="Elara", role="主角", importance_tier="A")
    )
    ts.upsert_character_state(CharacterState(character_id="elara"))
    return ts


# ------------------------------------------------------------------
# AgentRuntimeState 新字段
# ------------------------------------------------------------------


def test_agent_runtime_state_has_hallucination_fields() -> None:
    rs = AgentRuntimeState(agent_id="x")
    assert rs.hallucination_hits == 0
    assert rs.degrade_recommendations == 0
    assert rs.last_degrade_recommended_tick == 0


# ------------------------------------------------------------------
# TickState API
# ------------------------------------------------------------------


def test_record_degrade_recommendation_increments(tmp_path) -> None:
    ts = _ts(tmp_path)
    ts.record_degrade_recommendation(
        agent_id="character_agent:elara", tick=10, hits=4
    )
    rs = ts.get_agent_runtime_state("character_agent:elara")
    assert rs is not None
    assert rs.degrade_recommendations == 1
    assert rs.hallucination_hits == 4
    assert rs.last_degrade_recommended_tick == 10


def test_record_degrade_recommendation_accumulates(tmp_path) -> None:
    ts = _ts(tmp_path)
    ts.record_degrade_recommendation("x", tick=10, hits=4)
    ts.record_degrade_recommendation("x", tick=15, hits=2)
    rs = ts.get_agent_runtime_state("x")
    assert rs is not None
    assert rs.degrade_recommendations == 2
    assert rs.hallucination_hits == 6
    assert rs.last_degrade_recommended_tick == 15  # 取最新


def test_get_hallucination_stats_returns_per_agent_dict(tmp_path) -> None:
    ts = _ts(tmp_path)
    ts.record_degrade_recommendation("character_agent:elara", tick=10, hits=4)
    ts.record_degrade_recommendation("character_agent:zoe", tick=12, hits=2)
    stats = ts.get_hallucination_stats()
    assert "character_agent:elara" in stats
    assert stats["character_agent:elara"]["degrade_recommendations"] == 1
    assert stats["character_agent:elara"]["hallucination_hits"] == 4
    assert stats["character_agent:zoe"]["hallucination_hits"] == 2


def test_get_hallucination_stats_excludes_zero(tmp_path) -> None:
    """从未被建议过降级的 agent 不应出现在统计里 (即使有 AgentRuntimeState)。"""
    ts = _ts(tmp_path)
    ts.upsert_agent_runtime_state(
        AgentRuntimeState(agent_id="character_agent:clean", failure_count=2)
    )
    stats = ts.get_hallucination_stats()
    assert "character_agent:clean" not in stats


# ------------------------------------------------------------------
# Orchestrator 阶段 7 自动消费
# ------------------------------------------------------------------


def _make_orch(ts: TickState) -> Orchestrator:
    return Orchestrator(
        tick_state=ts,
        world_simulator=None,  # type: ignore[arg-type]
        character_agents={},
        narrator=None,  # type: ignore[arg-type]
        action_resolver=ActionResolver(),
    )


def test_ingest_guardian_output_writes_stats_in_shadow_mode(
    tmp_path, monkeypatch
) -> None:
    """默认 (无 env flag) 写 stats, 但不设 model_tier_override。"""
    monkeypatch.delenv("HALLUCINATION_AUTO_DEGRADE", raising=False)
    ts = _ts(tmp_path)
    orch = _make_orch(ts)
    out = GuardianOutput(
        conflicts=[
            GuardianConflict(
                id="hallucination_elara",
                type="character",
                priority="B",
                details="角色 elara 在最近 10 个 character_action 中, 4 次幻觉",
                evidence=["inventory_without_action", "location_without_move"],
                resolution_method="state_update",
                resolution_specifics="建议为该 agent 设 model_tier_override='haiku'",
            )
        ]
    )
    orch._ingest_guardian_conflicts(out, tick=20)
    rs = ts.get_agent_runtime_state("character_agent:elara")
    assert rs is not None
    assert rs.degrade_recommendations == 1
    assert rs.hallucination_hits == 2  # evidence 数 (flag 类型计数)
    assert rs.model_tier_override == ""  # shadow mode 不写


def test_ingest_guardian_output_writes_override_when_flag_on(
    tmp_path, monkeypatch
) -> None:
    """HALLUCINATION_AUTO_DEGRADE=1 时, 设 model_tier_override='haiku'。"""
    monkeypatch.setenv("HALLUCINATION_AUTO_DEGRADE", "1")
    ts = _ts(tmp_path)
    orch = _make_orch(ts)
    out = GuardianOutput(
        conflicts=[
            GuardianConflict(
                id="hallucination_elara",
                type="character",
                priority="B",
                details="角色 elara 幻觉率过高",
                evidence=["inventory_without_action"],
                resolution_specifics="建议 model_tier_override='haiku'",
            )
        ]
    )
    orch._ingest_guardian_conflicts(out, tick=20)
    rs = ts.get_agent_runtime_state("character_agent:elara")
    assert rs is not None
    assert rs.model_tier_override == "haiku"


def test_ingest_guardian_output_ignores_non_hallucination_conflicts(
    tmp_path, monkeypatch
) -> None:
    """只处理 id 以 hallucination_ 开头的 conflict, 其他类型 ignore。"""
    monkeypatch.delenv("HALLUCINATION_AUTO_DEGRADE", raising=False)
    ts = _ts(tmp_path)
    orch = _make_orch(ts)
    out = GuardianOutput(
        conflicts=[
            GuardianConflict(
                id="conflict_0",
                type="character",
                priority="A",
                details="一般连贯性问题",
            )
        ]
    )
    orch._ingest_guardian_conflicts(out, tick=20)
    assert ts.get_agent_runtime_state("character_agent:elara") is None


def test_ingest_guardian_output_extracts_character_id_from_details(
    tmp_path, monkeypatch
) -> None:
    """character_id 从 conflict.id 提取: hallucination_<character_id>。"""
    monkeypatch.delenv("HALLUCINATION_AUTO_DEGRADE", raising=False)
    ts = _ts(tmp_path)
    orch = _make_orch(ts)
    out = GuardianOutput(
        conflicts=[
            GuardianConflict(
                id="hallucination_zoe",
                type="character",
                priority="B",
                details="角色 zoe 幻觉",
                evidence=["money_without_action"],
            )
        ]
    )
    orch._ingest_guardian_conflicts(out, tick=20)
    rs = ts.get_agent_runtime_state("character_agent:zoe")
    assert rs is not None
    assert rs.hallucination_hits == 1
