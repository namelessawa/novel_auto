"""Orchestrator 单 tick 全链路集成测试。

用 mock_llm fixture 注入可控的 WorldSimulator / CharacterAgent / NarratorAgent
LLM 响应,验证 7 阶段调度的端到端行为:
1. WorldSimulator 输出被吸收进 TickState
2. CharacterAgent 决策正确转换为 character_action Event
3. ActionResolver 冲突正确标注
4. NarratorAgent 阈值 / 跳过 / 产出三态切换正确
5. TickState 落盘 + recover
6. TickSummary 包含正确的 agents_called / events_generated
"""

from __future__ import annotations

import asyncio
import os

import pytest

from agents.character_agent import CharacterAgent
from agents.narrator_agent import NarratorAgent
from agents.orchestrator import Orchestrator
from agents.world_simulator import WorldSimulator
from memory.tick_state import TickState
from memory_system.models import (
    CharacterProfile,
    CharacterState,
    Event,
    Goal,
    TickLocation,
    WorldState,
)
from nf_core.action_resolver import ActionResolver


def _world_sim_response(world_time: int, narrative_value: int = 8) -> dict:
    return {
        "new_world_state": {
            "world_time": world_time,
            "era": "战国",
            "current_season": "秋",
            "weather": "晴",
            "locations": [
                {"id": "city", "name": "都城", "type": "city", "present_characters": []}
            ],
            "factions": [],
            "active_global_events": [],
            "world_rules": [],
        },
        "natural_events": [
            {
                "id": f"evt_nat_{world_time}",
                "tick": world_time,
                "type": "exogenous",
                "location": "city",
                "participants": [],
                "description": "城中出现异象,北门大火",
                "visible_to": ["all_in_location"],
                "narrative_value": narrative_value,
                "consequences": [],
            }
        ],
        "delta_summary": "时间向前流逝一日。",
    }


def _character_action_response(action_type: str = "speak", target: str = "bob") -> dict:
    return {
        "action_type": action_type,
        "target": target,
        "description": f"alice {action_type} {target}",
        "dialogue_spoken": "你好,鲍勃。",
        "dialogue_to_whom": [target],
        "intent": "试探鲍勃的态度",
        "internal_monologue": "他到底知道多少？",
        "emotional_shift": "焦虑",
        "completed_goal_ids": [],
        "new_goals": [],
        "abandoned_goal_ids": [],
        "newly_learned": ["鲍勃今晨出现在都城"],
        "newly_speculated": [],
        "flags": [],
    }


def _narrator_response(text: str) -> dict:
    return {
        "narrative_text": text,
        "estimated_length": "short",
        "viewpoint_characters": ["alice"],
        "scene_focus": "alice 与 bob 重逢",
        "events_consumed": ["evt_nat_1"],
        "open_loops_referenced": [],
        "newly_opened_loops": [
            {
                "description": "鲍勃为何知情",
                "involved_characters": ["alice", "bob"],
                "type": "mystery",
                "urgency": 7,
            }
        ],
        "style_diagnostics": {"avg_sentence_length": 14, "rhetoric_density": "low"},
        "consistency_flags": [],
    }


def _bootstrap_state(data_dir: str) -> TickState:
    ts = TickState(data_dir=data_dir)
    ts.set_world_state(
        WorldState(
            world_time=0,
            era="战国",
            locations=[TickLocation(id="city", name="都城", type="city")],
        )
    )
    ts.upsert_character_profile(
        CharacterProfile(
            id="alice",
            name="Alice",
            age=28,
            role="主角",
            importance_tier="A",
            personality="谨慎",
            speech_style="短句",
            core_values=["守诺"],
            fears=["失败"],
            desires=["真相"],
        )
    )
    ts.upsert_character_profile(
        CharacterProfile(id="bob", name="Bob", role="配角", importance_tier="B")
    )
    ts.upsert_character_state(
        CharacterState(
            character_id="alice",
            current_location="city",
            arc_goal="揭开父亲死因",
            arc_progress=0.1,
            known_facts=["父亲十年前死于都城"],
        )
    )
    ts.upsert_character_state(
        CharacterState(
            character_id="bob",
            current_location="city",
            known_facts=["alice 是故人"],
        )
    )
    return ts


def _build_orchestrator(ts: TickState) -> Orchestrator:
    sim = WorldSimulator()
    narrator = NarratorAgent(strong_model_until_tick=0)  # 全程使用默认层级
    resolver = ActionResolver()
    agents = {
        "alice": CharacterAgent(ts.get_character_profile("alice")),
        "bob": CharacterAgent(ts.get_character_profile("bob")),
    }
    return Orchestrator(
        tick_state=ts,
        world_simulator=sim,
        character_agents=agents,
        narrator=narrator,
        action_resolver=resolver,
        main_tracking_character_id="alice",
    )


def test_single_tick_produces_summary_and_narrative(tmp_path, mock_llm) -> None:
    """全链路:WorldSimulator → CharacterAgent(alice + bob) → Narrator → 落盘。"""
    mock_llm.set_responses(
        [
            _world_sim_response(world_time=1),
            _character_action_response("speak", "bob"),  # alice
            _character_action_response("speak", "alice"),  # bob
            _narrator_response("秋风过城,二人相对而坐。"),
        ]
    )

    ts = _bootstrap_state(str(tmp_path))
    orch = _build_orchestrator(ts)
    summary = asyncio.run(orch.run_tick())

    assert summary.tick == 1
    assert summary.world_time == 1
    assert summary.narrator_produced_text is True
    assert summary.narrator_output_chars > 0
    assert "world_simulator" in summary.agents_called
    assert "narrator" in summary.agents_called
    # WorldSimulator 自然事件 + 两个 character_action = 至少 3 个事件
    assert len(summary.events_generated) >= 3

    # 叙述文件应写到 data_dir/narratives/tick_000001.txt
    narrative_path = tmp_path / "narratives" / "tick_000001.txt"
    assert narrative_path.is_file()
    assert "秋风过城" in narrative_path.read_text(encoding="utf-8")

    # OpenLoop 被新增到 TickState
    assert ts.get_open_loop_count() == 1
    loop = ts.get_open_loops()[0]
    assert "鲍勃为何知情" in loop.description

    # tick_state.json 持久化落盘
    assert (tmp_path / "tick_state.json").is_file()

    # alice 的 known_facts 应被 CharacterAgent 的 newly_learned 扩展
    alice_state = ts.get_character_state("alice")
    assert "鲍勃今晨出现在都城" in alice_state.known_facts
    assert alice_state.emotional_state == "焦虑"


def test_low_value_events_skip_narration(tmp_path, mock_llm) -> None:
    """事件价值过低 + 距上次叙述很近 → Narrator 应跳过,不消耗 LLM。"""
    # WorldSimulator 输出价值=1 的事件,无 CharacterAgent 决策(无可见事件触发)
    low_value_sim = _world_sim_response(world_time=1, narrative_value=1)
    low_value_sim["natural_events"][0]["visible_to"] = []  # 无角色可见 → 不触发 CharacterAgent

    mock_llm.set_responses(
        [
            low_value_sim,
            # 没有 character / narrator 响应 - 如果跳过逻辑正确就不会消费
        ]
    )

    ts = _bootstrap_state(str(tmp_path))
    ts.mark_narration(0)  # 上次叙述就在 tick 0
    orch = _build_orchestrator(ts)
    summary = asyncio.run(orch.run_tick())

    assert summary.narrator_produced_text is False
    assert summary.narrator_output_chars == 0


def test_tick_state_persisted_and_restored_across_runs(tmp_path, mock_llm) -> None:
    """跑两个 tick,验证第二个 Orchestrator 实例 load() 后从 tick=2 继续。"""
    mock_llm.set_responses(
        [
            _world_sim_response(world_time=1),
            _character_action_response(),
            _character_action_response(),
            _narrator_response("第一日叙述。"),
            _world_sim_response(world_time=2),
            _character_action_response(),
            _character_action_response(),
            _narrator_response("第二日叙述。"),
        ]
    )

    ts1 = _bootstrap_state(str(tmp_path))
    orch1 = _build_orchestrator(ts1)
    asyncio.run(orch1.run_tick())
    s2 = asyncio.run(orch1.run_tick())
    assert s2.tick == 2

    # 用新 TickState 实例,验证 load 后能从 tick 3 继续
    ts2 = TickState(data_dir=str(tmp_path))
    assert ts2.load() is True
    assert ts2.current_tick == 2
    assert ts2.world_time == 2
    assert ts2.get_open_loop_count() == 2  # 两次叙述各开一条新 loop


def test_action_conflict_logged_in_agents_called(tmp_path, mock_llm) -> None:
    """两个角色 fight 同一目标 → ActionResolver 标注冲突,Orchestrator 上报。"""
    # 让两个事件参与者都被波及触发 CharacterAgent
    sim = _world_sim_response(world_time=1)
    sim["natural_events"][0]["visible_to"] = ["all"]
    # 都 fight dragon
    alice_action = _character_action_response("fight", "dragon")
    bob_action = _character_action_response("fight", "dragon")

    mock_llm.set_responses(
        [
            sim,
            alice_action,
            bob_action,
            _narrator_response("决斗一触即发。"),
        ]
    )

    ts = _bootstrap_state(str(tmp_path))
    orch = _build_orchestrator(ts)
    summary = asyncio.run(orch.run_tick())

    # action_resolver 应被记录为 conflicts > 0
    conflict_marker = [a for a in summary.agents_called if a.startswith("action_resolver")]
    assert conflict_marker, f"expected action_resolver mention, got {summary.agents_called}"
    assert "conflicts=1" in conflict_marker[0]


def test_external_inject_event_appears_in_next_tick(tmp_path, mock_llm) -> None:
    """inject_event 注入的事件应在下一个 tick 的事件流中出现。"""
    injected = Event(
        id="evt_external",
        tick=1,
        type="dramatic",
        location="city",
        participants=["alice"],
        description="陌生人在城门留下血书",
        visible_to=["alice"],
        narrative_value=8,
    )

    mock_llm.set_responses(
        [
            _world_sim_response(world_time=1),
            # 两个角色都被 all_in_location 触发,加上 alice 被外部事件触发
            _character_action_response("investigate", "城门"),  # alice
            _character_action_response("wait", "city"),  # bob
            _narrator_response("alice 注视着血书,心中惊雷。"),
        ]
    )

    ts = _bootstrap_state(str(tmp_path))
    orch = _build_orchestrator(ts)
    orch.inject_event(injected)
    summary = asyncio.run(orch.run_tick())

    assert "evt_external" in summary.events_generated
    assert summary.narrator_produced_text is True
