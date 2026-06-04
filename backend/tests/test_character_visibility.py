"""CharacterAgent._filter_visible_events 可见性矩阵 (v2.21)。

回归 P0:此前 ``all_in_location`` 不校验位置, 任意带此标记的事件都泄露给
所有被唤醒角色, 违反戏剧根基"角色只看自己知道的"。

矩阵覆盖:
- cid in visible_to    → 始终可见
- 'all' in visible_to  → 真·全局, 始终可见
- 'all_in_location' + 位置匹配 → 可见
- 'all_in_location' + 位置不匹配 → 不可见  ← v2.20 之前是 bug
- 'all_in_location' + 角色位置空 → 不可见 (避免位置未知误并入广播)
- 全部不匹配 → 不可见
"""

from __future__ import annotations

import pytest

from agents.character_agent import CharacterAgent
from memory_system.models import CharacterProfile, Event


def _profile(cid: str = "diana") -> CharacterProfile:
    return CharacterProfile(
        id=cid,
        name=cid.title(),
        age=30,
        role="主角",
        importance_tier="A",
    )


def _event(visible_to: list[str], location: str = "throne_room") -> Event:
    return Event(
        id=f"evt_{location}_{'_'.join(visible_to) or 'none'}",
        tick=1,
        type="dramatic",
        location=location,
        participants=[],
        description="x",
        visible_to=visible_to,
        narrative_value=3,
    )


def test_explicit_cid_in_visible_to_always_seen():
    agent = CharacterAgent(_profile("diana"))
    e = _event(visible_to=["diana"], location="kitchen")
    # 角色当前在 throne_room, 事件在 kitchen, 但显式点名 → 仍可见
    assert agent._filter_visible_events([e], cur_location="throne_room") == [e]


def test_all_visible_to_always_seen():
    agent = CharacterAgent(_profile("diana"))
    e = _event(visible_to=["all"], location="far_away")
    assert agent._filter_visible_events([e], cur_location="throne_room") == [e]


def test_all_in_location_matching_seen():
    agent = CharacterAgent(_profile("diana"))
    e = _event(visible_to=["all_in_location"], location="throne_room")
    assert agent._filter_visible_events([e], cur_location="throne_room") == [e]


def test_all_in_location_mismatch_not_seen():
    """v2.21 核心回归:位置不匹配的 all_in_location 不再泄露。"""
    agent = CharacterAgent(_profile("diana"))
    e = _event(visible_to=["all_in_location"], location="kitchen")
    assert agent._filter_visible_events([e], cur_location="throne_room") == []


def test_all_in_location_empty_cur_location_not_seen():
    """角色位置空字符串时, all_in_location 一律不可见。"""
    agent = CharacterAgent(_profile("diana"))
    e = _event(visible_to=["all_in_location"], location="throne_room")
    assert agent._filter_visible_events([e], cur_location="") == []


def test_all_in_location_empty_event_location_not_seen():
    """事件位置空时即便 cur_location 也空, 不可见 (避免 '' == '' 误命中)。"""
    agent = CharacterAgent(_profile("diana"))
    e = _event(visible_to=["all_in_location"], location="")
    assert agent._filter_visible_events([e], cur_location="") == []


def test_no_visibility_match_filtered():
    agent = CharacterAgent(_profile("diana"))
    e = _event(visible_to=["bob"], location="throne_room")
    assert agent._filter_visible_events([e], cur_location="throne_room") == []


def test_mixed_batch_preserves_order_and_filters():
    agent = CharacterAgent(_profile("diana"))
    e1 = _event(visible_to=["diana"], location="kitchen")           # in
    e2 = _event(visible_to=["bob"], location="throne_room")          # out
    e3 = _event(visible_to=["all"], location="far")                  # in
    e4 = _event(visible_to=["all_in_location"], location="kitchen")  # out (loc mismatch)
    e5 = _event(visible_to=["all_in_location"], location="throne_room")  # in (loc match)

    visible = agent._filter_visible_events(
        [e1, e2, e3, e4, e5], cur_location="throne_room"
    )
    assert visible == [e1, e3, e5]
