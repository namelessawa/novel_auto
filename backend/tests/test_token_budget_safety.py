"""Tests for TokenBudgetTracker + SafetyFilter (v2.7)。"""

from __future__ import annotations

import re

import pytest

from narrative.safety_filter import (
    DEFAULT_RULES,
    SafetyFilter,
    SafetyRule,
)
from nf_core.token_budget import (
    TokenBudgetTracker,
    get_global_tracker,
    set_global_tracker,
)


# ---------------------------------------------------------------------------
# TokenBudgetTracker — 记账
# ---------------------------------------------------------------------------


def test_record_increments_totals(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path))
    t.record(
        agent_id="narrator",
        priority="critical",
        prompt_tokens=100,
        completion_tokens=200,
    )
    snap = t.snapshot
    assert snap.total_prompt_tokens == 100
    assert snap.total_completion_tokens == 200
    assert snap.total_tokens == 300
    assert snap.by_agent["narrator"] == 300
    assert snap.by_priority["critical"] == 300
    assert snap.call_count == 1


def test_record_aggregates_across_agents(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path))
    t.record(agent_id="narrator", priority="critical", prompt_tokens=100, completion_tokens=100)
    t.record(agent_id="critic", priority="medium", prompt_tokens=50, completion_tokens=50)
    t.record(agent_id="critic", priority="medium", prompt_tokens=20, completion_tokens=20)
    snap = t.snapshot
    assert snap.by_agent["narrator"] == 200
    assert snap.by_agent["critic"] == 140
    assert snap.call_count == 3


def test_begin_tick_resets_tick_tokens(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path), max_per_tick_tokens=1000)
    t.record(
        agent_id="x", priority="medium",
        prompt_tokens=400, completion_tokens=400, tick=10,
    )
    assert t.remaining_tick() == 200
    t.begin_tick(11)
    assert t.remaining_tick() == 1000


# ---------------------------------------------------------------------------
# TokenBudgetTracker — 决策
# ---------------------------------------------------------------------------


def test_no_limit_allows_everything(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path))
    assert t.can_afford(priority="optional", estimated_tokens=1_000_000) is True


def test_critical_always_allowed(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path), max_total_tokens=1000)
    t.record(agent_id="x", priority="medium", prompt_tokens=2000, completion_tokens=0)
    # 总预算已超, 但 critical 仍允许
    assert t.can_afford(priority="critical", estimated_tokens=500) is True


def test_optional_blocked_at_70_percent(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path), max_total_tokens=1000)
    t.record(agent_id="x", priority="medium", prompt_tokens=700, completion_tokens=0)
    # 已 70%, 估算后会更高 → optional 拒绝
    assert t.can_afford(priority="optional", estimated_tokens=100) is False


def test_medium_blocked_at_90_percent(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path), max_total_tokens=1000)
    t.record(agent_id="x", priority="medium", prompt_tokens=900, completion_tokens=0)
    assert t.can_afford(priority="medium", estimated_tokens=100) is False


def test_per_tick_limit_optional_blocked_at_80(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path), max_per_tick_tokens=1000)
    t.record(
        agent_id="x", priority="medium",
        prompt_tokens=700, completion_tokens=0, tick=5,
    )
    assert t.can_afford(priority="optional", estimated_tokens=200) is False


# ---------------------------------------------------------------------------
# TokenBudgetTracker — 持久化
# ---------------------------------------------------------------------------


def test_save_load_roundtrip(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path))
    t.record(agent_id="narrator", priority="critical", prompt_tokens=100, completion_tokens=100)
    t.record(agent_id="critic", priority="medium", prompt_tokens=50, completion_tokens=50)
    t.save()

    fresh = TokenBudgetTracker(str(tmp_path))
    assert fresh.load() is True
    assert fresh.snapshot.total_tokens == 300
    assert fresh.snapshot.by_agent["narrator"] == 200


def test_load_missing_returns_false(tmp_path) -> None:
    t = TokenBudgetTracker(str(tmp_path))
    assert t.load() is False


# ---------------------------------------------------------------------------
# Global tracker
# ---------------------------------------------------------------------------


def test_global_tracker_singleton_swap(tmp_path) -> None:
    custom = TokenBudgetTracker(str(tmp_path))
    set_global_tracker(custom)
    assert get_global_tracker() is custom


# ---------------------------------------------------------------------------
# SafetyFilter
# ---------------------------------------------------------------------------


def test_safety_filter_blocks_id_card() -> None:
    f = SafetyFilter()
    text = "他递过身份证: 110101199001019999, 转身离开。"
    res = f.check(text)
    assert res.is_blocked is True
    assert any(h.rule_id == "PII_ID_CARD" for h in res.hits)


def test_safety_filter_blocks_cn_phone() -> None:
    f = SafetyFilter()
    text = "她念出号码: 13800138000"
    res = f.check(text)
    assert res.is_blocked is True
    assert any(h.rule_id == "PII_PHONE_CN" for h in res.hits)


def test_safety_filter_warns_email_masks() -> None:
    f = SafetyFilter()
    text = "信末签着 alice@example.com 几个字。"
    res = f.check(text)
    assert res.is_blocked is False
    assert any(h.rule_id == "PII_EMAIL" for h in res.hits)


def test_safety_filter_passes_literary_violence() -> None:
    """文学暴力不应被阻止。"""
    f = SafetyFilter()
    text = "他举起剑, 刺穿对方的咽喉, 鲜血溅在岩石上。"
    res = f.check(text)
    assert res.is_blocked is False
    assert res.hits == []


def test_safety_filter_blocks_harm_instruction() -> None:
    f = SafetyFilter()
    text = "她在纸上写: 具体方法 1: 先准备绳子, 然后选择上吊自杀。"
    res = f.check(text)
    assert res.is_blocked is True
    assert any(h.category == "harm" for h in res.hits)


def test_safety_filter_passes_grief_description() -> None:
    """悲剧/创伤描写不应触发 harm 规则。"""
    f = SafetyFilter()
    text = "她跪在墓前, 想起母亲临终前的疲倦。"
    res = f.check(text)
    assert res.is_blocked is False


def test_safety_filter_empty_text_returns_clean() -> None:
    f = SafetyFilter()
    res = f.check("")
    assert res.is_blocked is False
    assert res.hits == []


def test_safety_filter_custom_rule() -> None:
    f = SafetyFilter(rules=tuple(DEFAULT_RULES))
    f.add_rule(
        SafetyRule(
            rule_id="CUSTOM_TEST",
            pattern=re.compile(r"禁词测试"),
            severity="block",
            category="custom",
            description="测试用",
        )
    )
    res = f.check("这里有禁词测试出现")
    assert res.is_blocked is True
    assert any(h.rule_id == "CUSTOM_TEST" for h in res.hits)
