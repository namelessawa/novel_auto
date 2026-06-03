"""Model tier override 激活层 (v2.18 Phase 6)。

闭环最后一公里: AgentRuntimeState.model_tier_override → CharacterAgent.decide
→ LLMClient.chat(model_override=...)。

测试三层:
1. LLMClient.chat 接受 model_override 参数, 用它替代 self._model
2. CharacterAgent.decide(model_override=...) 透传到 chat
3. batch_decide(model_overrides={cid: tier}) 按 character_id 分发
4. Orchestrator 阶段 3 从 TickState 读 model_tier_override 自动注入
"""

from __future__ import annotations

import pytest

from agents.character_agent import CharacterAgent
from agents.orchestrator import Orchestrator
from memory.tick_state import TickState
from memory_system.models import (
    AgentRuntimeState,
    CharacterProfile,
    CharacterState,
    Event,
    TickLocation,
    WorldState,
)
from nf_core.action_resolver import ActionResolver


def _profile(cid: str = "elara", tier: str = "A") -> CharacterProfile:
    return CharacterProfile(id=cid, name=cid, role="主角", importance_tier=tier)


def _state(cid: str = "elara") -> CharacterState:
    return CharacterState(character_id=cid, current_location="loc_city")


def _action_payload() -> dict:
    return {
        "action_type": "wait",
        "target": "",
        "description": "原地等待",
        "internal_monologue": "...",
    }


# ------------------------------------------------------------------
# CharacterAgent.decide 透传
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decide_without_override_passes_none(mock_llm) -> None:
    """默认不传 model_override 时, chat 的 kw 不含 model_override (或值为 None)。"""
    mock_llm.set_responses([_action_payload()])
    agent = CharacterAgent(profile=_profile())
    await agent.decide(_state(), all_tick_events=[])
    assert len(mock_llm.call_kwargs) == 1
    kw = mock_llm.call_kwargs[0]
    assert kw.get("model_override") in (None, "")


@pytest.mark.asyncio
async def test_decide_with_override_passes_to_chat(mock_llm) -> None:
    mock_llm.set_responses([_action_payload()])
    agent = CharacterAgent(profile=_profile())
    await agent.decide(_state(), all_tick_events=[], model_override="haiku")
    kw = mock_llm.call_kwargs[0]
    assert kw.get("model_override") == "haiku"


# ------------------------------------------------------------------
# CharacterAgent.batch_decide 按 id 分发 override
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_decide_dispatches_overrides_per_character(mock_llm) -> None:
    mock_llm.set_responses([_action_payload(), _action_payload()])
    a = CharacterAgent(profile=_profile("elara", "A"))
    b = CharacterAgent(profile=_profile("zoe", "B"))
    actions = await CharacterAgent.batch_decide(
        [a, b],
        states={"elara": _state("elara"), "zoe": _state("zoe")},
        all_tick_events=[],
        model_overrides={"elara": "haiku"},
    )
    assert len(actions) == 2
    # 找到对应 character_id 的那次调用
    elara_call = next(
        kw for kw in mock_llm.call_kwargs if kw.get("agent_id") == "character_agent:elara"
    )
    zoe_call = next(
        kw for kw in mock_llm.call_kwargs if kw.get("agent_id") == "character_agent:zoe"
    )
    assert elara_call.get("model_override") == "haiku"
    assert zoe_call.get("model_override") in (None, "")


# ------------------------------------------------------------------
# Orchestrator 阶段 3 自动从 TickState 读 override
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_phase3_reads_override_from_tick_state(
    tmp_path, mock_llm
) -> None:
    """Orchestrator 应自动从 AgentRuntimeState.model_tier_override 注入 override。"""
    ts = TickState(data_dir=str(tmp_path))
    ts.set_world_state(
        WorldState(locations=[TickLocation(id="loc_city", name="新城")])
    )
    profile = _profile("elara", "A")
    ts.upsert_character_profile(profile)
    ts.upsert_character_state(_state("elara"))
    ts.upsert_agent_runtime_state(
        AgentRuntimeState(
            agent_id="character_agent:elara", model_tier_override="haiku"
        )
    )

    agent = CharacterAgent(profile=profile)
    orch = Orchestrator(
        tick_state=ts,
        world_simulator=_StubWorldSim(),  # type: ignore[arg-type]
        character_agents={"elara": agent},
        narrator=_StubNarrator(),  # type: ignore[arg-type]
        action_resolver=ActionResolver(),
    )

    mock_llm.set_responses([_action_payload()])
    # 直接调阶段 3 — 用最小子集模拟 events 触发该角色
    visible_event = Event(
        id="evt_test",
        tick=1,
        type="exogenous",
        location="loc_city",
        participants=[],
        description="测试事件",
        visible_to=["elara"],
        narrative_value=5,
    )
    affected = orch._collect_affected_characters([visible_event])
    assert "elara" in affected
    # 模拟阶段 3 collect overrides + batch_decide
    overrides = orch._collect_model_overrides(affected, tick=1)
    assert overrides.get("elara") == "haiku"


# ------------------------------------------------------------------
# Stubs (避免拉真实 WorldSimulator/Narrator)
# ------------------------------------------------------------------


class _StubWorldSim:
    async def simulate(self, **kwargs):  # pragma: no cover — never called
        raise NotImplementedError


class _StubNarrator:
    async def narrate(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def set_exempt_words(self, words):  # pragma: no cover
        pass
