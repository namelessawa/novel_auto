"""ConsistencyGuardian 幻觉率监控 (v2.18)。

CharacterAgent 偶尔会在 action_type=speak 时随手填 inventory_added / new_location,
这是 LLM 幻觉。Phase 1-3 已让 Orchestrator 在 Event.consequences 里打
``inventory_without_action`` / ``location_without_move`` / ``money_without_action``
flag。

ConsistencyGuardian 在阶段 7 周期扫描时, 统计最近 N tick 这些 flag 的出现率,
超过阈值时:
* 产 GuardianConflict(priority='B', type='character',
                       details=该角色幻觉率过高, suggestion=降级建议)
* 提议 model_tier_override='haiku' 让 Orchestrator 下 tick 降级 (后续接入)。
"""

from __future__ import annotations

from agents.consistency_guardian import ConsistencyGuardian
from memory_system.models import Event


def _evt(
    tick: int,
    char_id: str,
    consequences: list[str],
    desc: str = "",
) -> Event:
    return Event(
        id=f"evt_{tick}_{char_id}",
        tick=tick,
        type="character_action",
        location="loc_city",
        participants=[char_id],
        description=desc or f"{char_id} acted",
        visible_to=[char_id],
        narrative_value=0,
        consequences=list(consequences),
    )


def test_scan_hallucination_rate_empty_returns_nothing() -> None:
    """无事件 / 无 flag 时, 不应产任何 conflict。"""
    g = ConsistencyGuardian()
    conflicts = g.scan_hallucination_rate(events=[], threshold=0.3)
    assert conflicts == []


def test_scan_hallucination_rate_below_threshold_silent() -> None:
    """1/10 = 10% 低于 30% 阈值 → 不报。"""
    g = ConsistencyGuardian()
    events = [_evt(i, "elara", []) for i in range(9)]
    events.append(_evt(10, "elara", ["inventory_without_action"]))
    conflicts = g.scan_hallucination_rate(events=events, threshold=0.3)
    assert conflicts == []


def test_scan_hallucination_rate_above_threshold_emits_conflict() -> None:
    """4/10 = 40% 超过 30% → 应产 GuardianConflict[B, character]。"""
    g = ConsistencyGuardian()
    events = [_evt(i, "elara", []) for i in range(6)]
    events.extend(
        [
            _evt(7, "elara", ["inventory_without_action"]),
            _evt(8, "elara", ["location_without_move"]),
            _evt(9, "elara", ["money_without_action"]),
            _evt(10, "elara", ["inventory_without_action"]),
        ]
    )
    conflicts = g.scan_hallucination_rate(events=events, threshold=0.3)
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.type == "character"
    assert c.priority == "B"
    assert "elara" in c.details
    # 应包含建议降级
    assert "haiku" in c.resolution_specifics or "degrade" in c.resolution_specifics.lower()


def test_scan_hallucination_rate_per_character() -> None:
    """两个角色独立统计, 只对超阈值的那个报。"""
    g = ConsistencyGuardian()
    events: list[Event] = []
    # elara: 4/4 全幻觉
    for i in range(1, 5):
        events.append(_evt(i, "elara", ["inventory_without_action"]))
    # zoe: 0/5 干净
    for i in range(5, 10):
        events.append(_evt(i, "zoe", []))
    conflicts = g.scan_hallucination_rate(events=events, threshold=0.3)
    assert len(conflicts) == 1
    assert "elara" in conflicts[0].details
    assert "zoe" not in conflicts[0].details


def test_scan_hallucination_rate_ignores_non_action_events() -> None:
    """exogenous / dramatic 事件不参与统计 — 它们没 character_id 主体。"""
    g = ConsistencyGuardian()
    exo = Event(
        id="exo_1",
        tick=1,
        type="exogenous",
        location="loc_city",
        participants=["elara"],
        description="陨石坠落",
        visible_to=["all"],
        narrative_value=8,
        consequences=["inventory_without_action"],  # 不应被算到 elara 头上
    )
    actions = [_evt(i, "elara", []) for i in range(10)]
    conflicts = g.scan_hallucination_rate(events=[exo] + actions, threshold=0.3)
    assert conflicts == []


def test_scan_hallucination_rate_threshold_boundary() -> None:
    """正好 = 阈值不报, 严格大于才报 (防边界震荡)。"""
    g = ConsistencyGuardian()
    # 3/10 = 0.3
    events = [_evt(i, "elara", []) for i in range(7)]
    events.extend(
        [
            _evt(8, "elara", ["inventory_without_action"]),
            _evt(9, "elara", ["inventory_without_action"]),
            _evt(10, "elara", ["inventory_without_action"]),
        ]
    )
    conflicts = g.scan_hallucination_rate(events=events, threshold=0.3)
    assert conflicts == []  # 等于阈值不报
