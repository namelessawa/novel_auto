"""CharacterAgent 中文约束验证 (v2.16)。

实测样本里出现过 "Diana uses sword..." 这类英文动作句污染事件日志。
本测试验证:
1. _parse_action 检测到 description / dialogue_spoken 含连续英文词时, 自动追加
   ``lang_contamination`` flag — 下游 (Narrator / 测试) 可据此降权或拒绝。
2. 纯中文行动不会误触发。
3. 含少量专有英文名 (单个) 不会触发。

我们没有完全拒绝英文输出 — 让 LLM 完全不出英文很难, 而 flag 已足以让 Narrator
忽略这条 action 或主动改写。"""

from __future__ import annotations

import json

import pytest

from agents.character_agent import CharacterAgent
from memory_system.models import CharacterProfile


def _profile() -> CharacterProfile:
    return CharacterProfile(
        id="diana",
        name="戴安娜",
        age=30,
        role="主角",
        importance_tier="A",
    )


def _make_payload(description: str, dialogue: str | None = None) -> str:
    return json.dumps(
        {
            "action_type": "fight",
            "target": "guard",
            "description": description,
            "dialogue_spoken": dialogue,
            "dialogue_to_whom": [],
            "intent": "突围",
            "internal_monologue": "必须撑住",
            "emotional_shift": "决绝",
            "completed_goal_ids": [],
            "new_goals": [],
            "abandoned_goal_ids": [],
            "newly_learned": [],
            "newly_speculated": [],
            "flags": [],
        },
        ensure_ascii=False,
    )


def test_english_run_in_description_flags_contamination():
    agent = CharacterAgent(_profile())
    raw = _make_payload(description="Diana uses sword to attack guard")

    action = agent._parse_action(raw)

    assert "lang_contamination" in action.flags


def test_english_run_in_dialogue_flags_contamination():
    agent = CharacterAgent(_profile())
    raw = _make_payload(
        description="戴安娜抽出长剑刺向北门守卫",
        dialogue="get out of my way",
    )

    action = agent._parse_action(raw)

    assert "lang_contamination" in action.flags


def test_pure_chinese_action_no_flag():
    agent = CharacterAgent(_profile())
    raw = _make_payload(
        description="戴安娜抽出长剑横劈, 守卫倒退两步",
        dialogue="退后。",
    )

    action = agent._parse_action(raw)

    assert "lang_contamination" not in action.flags


def test_single_english_name_no_flag():
    """单一英文专有名词 (如未本地化的角色名) 不应触发。"""
    agent = CharacterAgent(_profile())
    raw = _make_payload(
        description="戴安娜把信物交给 Marcus, 转身离开",
    )

    action = agent._parse_action(raw)

    assert "lang_contamination" not in action.flags


def test_new_state_fields_round_trip():
    """v2.16 — 解析新字段并保留: new_location / inventory_added / status_added /
    relationship_deltas 都应正确反序列化, 让 _apply_actions 能用。"""
    agent = CharacterAgent(_profile())
    raw = json.dumps(
        {
            "action_type": "move",
            "target": "loc_safehouse",
            "description": "潜入安全屋",
            "new_location": "loc_safehouse",
            "inventory_added": ["撬棍"],
            "inventory_removed": ["旧通讯器"],
            "status_added": ["疲惫"],
            "status_removed": [],
            "relationship_deltas": {
                "zoe": {
                    "trust_delta": 2,
                    "new_type": "盟友",
                    "history_entry": "通风管会合",
                }
            },
        },
        ensure_ascii=False,
    )

    action = agent._parse_action(raw)

    assert action.new_location == "loc_safehouse"
    assert "撬棍" in action.inventory_added
    assert "旧通讯器" in action.inventory_removed
    assert "疲惫" in action.status_added
    assert "zoe" in action.relationship_deltas
    rel_delta = action.relationship_deltas["zoe"]
    assert rel_delta.trust_delta == 2
    assert rel_delta.new_type == "盟友"
    assert rel_delta.history_entry == "通风管会合"
