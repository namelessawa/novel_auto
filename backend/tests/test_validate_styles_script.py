from __future__ import annotations

from scripts.validate_styles import (
    _is_transient_generation_failure,
    _normalise_semantic_judge,
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
