from __future__ import annotations

from scripts.validate_styles import (
    _aggregate_cost,
    _is_transient_generation_failure,
    _normalise_semantic_judge,
    _usage_delta,
)


def test_semantic_judge_cannot_pass_with_explicit_hard_gap() -> None:
    out = _normalise_semantic_judge({
        "pass": True,
        "score": 9,
        "issues": ["干冷旁白未独立成句，需单独提炼一句。"],
        "rewrite_directive": "",
    })
    assert out["pass"] is False
    assert out["blocking_issues"]
    assert out["rewrite_directive"]


def test_semantic_judge_keeps_non_blocking_observation() -> None:
    out = _normalise_semantic_judge({
        "pass": True,
        "score": 9,
        "issues": ["反讽力度可更尖锐，但硬契约均已完成。"],
        "blocking_issues": [],
    })
    assert out["pass"] is True
    assert out["blocking_issues"] == []


def test_semantic_judge_promotes_state_conflict_to_blocking() -> None:
    out = _normalise_semantic_judge({
        "pass": True,
        "score": 9,
        "state_conflicts": ["苏默的肋伤无事件依据转移给林雪"],
        "blocking_issues": [],
    })
    assert out["pass"] is False
    assert out["blocking_issues"] == ["苏默的肋伤无事件依据转移给林雪"]


def test_semantic_judge_promotes_explicit_unmet_contract_to_blocking() -> None:
    out = _normalise_semantic_judge({
        "pass": True,
        "score": 8,
        "issues": ["契约要求每段尾留他人动向空白，但各段未明确兑现。"],
        "blocking_issues": [],
    })
    assert out["pass"] is False
    assert out["blocking_issues"]


def test_only_empty_transient_generation_failures_are_retryable() -> None:
    assert _is_transient_generation_failure("", "LLM 不可用: Connection error.")
    assert _is_transient_generation_failure("", "Timeout after 600 seconds")
    assert not _is_transient_generation_failure("正文", "Connection error")
    assert not _is_transient_generation_failure("", "状态守卫未通过")


def test_semantic_judge_drops_self_negating_state_conflict() -> None:
    conflict = "苏莫建议交图虽不构成物理持有冲突，但缺乏林雪授权，非严格状态冲突。"
    out = _normalise_semantic_judge({
        "pass": True,
        "score": 8,
        "state_conflicts": [conflict],
        "blocking_issues": [conflict],
        "issues": [],
    })

    assert out["pass"] is True
    assert out["state_conflicts"] == []
    assert out["blocking_issues"] == []


def test_usage_delta_reports_agent_breakdown_and_missing_usage() -> None:
    before = {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "cached_tokens": 10,
        "call_count": 2,
        "by_agent": {"narrator": 120},
    }
    after = {
        "prompt_tokens": 250,
        "completion_tokens": 70,
        "cached_tokens": 40,
        "call_count": 4,
        "by_agent": {"narrator": 220, "style_validation_judge": 80},
    }

    delta = _usage_delta(before, after, 1.23456)

    assert delta == {
        "duration_sec": 1.235,
        "prompt_tokens": 150,
        "completion_tokens": 50,
        "total_tokens": 200,
        "cached_tokens": 30,
        "call_count": 2,
        "usage_status": "REPORTED",
        "by_agent": {"narrator": 100, "style_validation_judge": 80},
        "unattributed_tokens": 20,
    }
    missing = _usage_delta(before, {**before, "call_count": 3}, 0.5)
    assert missing["usage_status"] == "MISSING"


def test_aggregate_cost_never_turns_missing_usage_into_zero_cost() -> None:
    total = _aggregate_cost([
        {
            "duration_sec": 2.0,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cached_tokens": 1,
            "call_count": 1,
            "usage_status": "REPORTED",
            "by_agent": {"narrator": 15},
        },
        {
            "duration_sec": 3.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cached_tokens": 0,
            "call_count": 1,
            "usage_status": "MISSING",
            "by_agent": {},
        },
    ])

    assert total["total_tokens"] == 15
    assert total["usage_status"] == "PARTIAL"
    assert total["missing_usage_blocks"] == 1
    assert total["by_agent"] == {"narrator": 15}
    assert total["unattributed_tokens"] == 0
