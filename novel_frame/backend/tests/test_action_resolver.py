"""ActionResolver 行动冲突解析单元测试。"""

from __future__ import annotations

from memory_system.models import CharacterAction, CharacterProfile, Goal
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
