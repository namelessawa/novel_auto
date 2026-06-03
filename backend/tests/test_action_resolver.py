"""ActionResolver 行动冲突解析单元测试。"""

from __future__ import annotations

from memory_system.models import (
    CharacterAction,
    CharacterProfile,
    Goal,
    RelationshipDelta,
)
from nf_core.action_resolver import ActionResolver


def _profile(cid: str, tier: str = "B") -> CharacterProfile:
    return CharacterProfile(id=cid, name=cid, importance_tier=tier)


def test_no_conflict_returns_input_intact() -> None:
    ar = ActionResolver()
    actions = [
        CharacterAction(character_id="a", action_type="move", target="north"),
        CharacterAction(character_id="b", action_type="speak", target="a"),
    ]
    resolved, diag = ar.resolve(actions, profiles={"a": _profile("a"), "b": _profile("b")})
    assert diag.conflict_groups == 0
    assert diag.losers == 0
    assert [r.action_type for r in resolved] == ["move", "speak"]


def test_two_chars_fight_same_target_tier_a_wins() -> None:
    ar = ActionResolver()
    actions = [
        CharacterAction(character_id="b_char", action_type="fight", target="dragon"),
        CharacterAction(character_id="a_char", action_type="fight", target="dragon"),
    ]
    profiles = {
        "a_char": _profile("a_char", tier="A"),
        "b_char": _profile("b_char", tier="B"),
    }
    resolved, diag = ar.resolve(actions, profiles=profiles)
    assert diag.conflict_groups == 1
    assert diag.losers == 1
    assert diag.winner_by_group["fight:dragon"] == "a_char"

    by_id = {r.character_id: r for r in resolved}
    assert by_id["a_char"].action_type == "fight"
    assert by_id["b_char"].action_type == "wait"
    assert any(f.startswith("conflict_lost:a_char") for f in by_id["b_char"].flags)


def test_same_tier_higher_goal_priority_wins() -> None:
    ar = ActionResolver()
    actions = [
        CharacterAction(
            character_id="b",
            action_type="take",
            target="amulet",
            new_goals=[Goal(id="g1", description="grab amulet", priority=3)],
        ),
        CharacterAction(
            character_id="a",
            action_type="take",
            target="amulet",
            new_goals=[Goal(id="g2", description="claim amulet", priority=9)],
        ),
    ]
    profiles = {"a": _profile("a", "B"), "b": _profile("b", "B")}
    resolved, _ = ar.resolve(actions, profiles=profiles)
    by_id = {r.character_id: r for r in resolved}
    assert by_id["a"].action_type == "take"
    assert by_id["b"].action_type == "wait"


def test_non_exclusive_actions_never_conflict() -> None:
    ar = ActionResolver()
    actions = [
        CharacterAction(character_id="a", action_type="speak", target="town"),
        CharacterAction(character_id="b", action_type="speak", target="town"),
        CharacterAction(character_id="c", action_type="move", target="north"),
        CharacterAction(character_id="d", action_type="move", target="north"),
    ]
    profiles = {cid: _profile(cid) for cid in ["a", "b", "c", "d"]}
    _, diag = ar.resolve(actions, profiles=profiles)
    assert diag.conflict_groups == 0


def test_empty_target_not_grouped() -> None:
    """无明确 target 的独占类不参与冲突分桶。"""
    ar = ActionResolver()
    actions = [
        CharacterAction(character_id="a", action_type="fight", target=""),
        CharacterAction(character_id="b", action_type="fight", target=""),
    ]
    profiles = {"a": _profile("a"), "b": _profile("b")}
    _, diag = ar.resolve(actions, profiles=profiles)
    assert diag.conflict_groups == 0


def test_empty_input_returns_empty() -> None:
    ar = ActionResolver()
    resolved, diag = ar.resolve([], profiles={})
    assert resolved == []
    assert diag.conflict_groups == 0


def test_missing_profile_falls_back_to_lowest_priority() -> None:
    ar = ActionResolver()
    actions = [
        CharacterAction(character_id="known", action_type="claim", target="throne"),
        CharacterAction(character_id="unknown_orphan", action_type="claim", target="throne"),
    ]
    profiles = {"known": _profile("known", tier="C")}
    resolved, diag = ar.resolve(actions, profiles=profiles)
    # known (tier C) 应胜 unknown_orphan (无 profile => rank 9)
    assert diag.winner_by_group["claim:throne"] == "known"
    by_id = {r.character_id: r for r in resolved}
    assert by_id["known"].action_type == "claim"
    assert by_id["unknown_orphan"].action_type == "wait"


def test_loser_inventory_added_is_cleared() -> None:
    """败者 take/fight 失败后, 不应仍写入 inventory_added — 否则两人都"拿到"同一物品。

    建议核心: "失败者的状态变更必须被取消或降级, 不能仍然获得物品/完成行动"。
    """
    ar = ActionResolver()
    actions = [
        CharacterAction(
            character_id="winner",
            action_type="take",
            target="sword",
            inventory_added=["sword"],
        ),
        CharacterAction(
            character_id="loser",
            action_type="take",
            target="sword",
            inventory_added=["sword"],
        ),
    ]
    profiles = {
        "winner": _profile("winner", tier="A"),
        "loser": _profile("loser", tier="B"),
    }
    resolved, diag = ar.resolve(actions, profiles=profiles)
    assert diag.winner_by_group["take:sword"] == "winner"
    by_id = {r.character_id: r for r in resolved}
    assert by_id["winner"].inventory_added == ["sword"]
    # 败者必须被清空, 否则阶段 5 _apply_actions 仍会把 sword 写入其 inventory
    assert by_id["loser"].inventory_added == []


def test_loser_hard_state_fields_are_all_cleared() -> None:
    """败者的全部硬状态字段都应清零: new_location / status_added / relationship_deltas。

    主动卸下/解除 (inventory_removed / status_removed) 不在清零之列 — 即使
    冲突失败, 角色仍可决定"丢掉手里的剑"或"挣脱中毒状态"。
    """
    ar = ActionResolver()
    actions = [
        CharacterAction(
            character_id="winner",
            action_type="fight",
            target="throne_room",
            new_location="throne_room",
            status_added=["王者光环"],
            inventory_removed=["旧匕首"],
        ),
        CharacterAction(
            character_id="loser",
            action_type="fight",
            target="throne_room",
            new_location="throne_room",
            inventory_added=["王冠"],
            status_added=["胜利的喜悦"],
            inventory_removed=["旧绳索"],
            status_removed=["紧张"],
            relationship_deltas={
                "winner": RelationshipDelta(trust_delta=5, new_type="盟友"),
            },
        ),
    ]
    profiles = {
        "winner": _profile("winner", tier="A"),
        "loser": _profile("loser", tier="B"),
    }
    resolved, _ = ar.resolve(actions, profiles=profiles)
    by_id = {r.character_id: r for r in resolved}

    # 赢家原状态变更必须保留
    assert by_id["winner"].new_location == "throne_room"
    assert by_id["winner"].status_added == ["王者光环"]

    # 败者: 改写得到的"成果"必须清零
    assert by_id["loser"].new_location == ""
    assert by_id["loser"].inventory_added == []
    assert by_id["loser"].status_added == []
    assert by_id["loser"].relationship_deltas == {}

    # 败者: 主动"丢"的转移允许保留 — 失败也可以扔东西/挣脱
    assert by_id["loser"].inventory_removed == ["旧绳索"]
    assert by_id["loser"].status_removed == ["紧张"]


def test_winner_with_single_contender_keeps_hard_fields() -> None:
    """单一 contender (无冲突) 时, 硬字段绝对不能被清零。"""
    ar = ActionResolver()
    actions = [
        CharacterAction(
            character_id="solo",
            action_type="take",
            target="amulet",
            inventory_added=["amulet"],
            new_location="loc_tomb",
        ),
    ]
    profiles = {"solo": _profile("solo", tier="A")}
    resolved, diag = ar.resolve(actions, profiles=profiles)
    assert diag.conflict_groups == 0
    assert resolved[0].inventory_added == ["amulet"]
    assert resolved[0].new_location == "loc_tomb"
