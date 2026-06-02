"""PromptBuilder 单元测试 - 验证 token 预算与裁剪策略。"""

from __future__ import annotations

from nf_core.prompt_builder import PromptBuilder, PromptSection


def test_no_truncation_when_under_budget() -> None:
    pb = PromptBuilder(budget=2000)
    result = pb.build(
        [
            PromptSection("系统指令", "你是叙述者", priority=1),
            PromptSection("当前状态", "tick=42", priority=3),
        ]
    )
    assert result.over_budget is False
    assert "系统指令" in result.text
    assert "当前状态" in result.text
    assert result.sections_dropped == []


def test_low_priority_dropped_first_when_over_budget() -> None:
    pb = PromptBuilder(budget=100)
    big_content = "x" * 1000
    result = pb.build(
        [
            PromptSection("必保留", "重要", priority=1),
            PromptSection("可压缩", big_content, priority=3),
            PromptSection("可丢弃", big_content, priority=5),
        ]
    )
    # priority=1 必须留,priority=5 应在 priority=3 之前 drop
    assert "必保留" in result.text
    assert "可丢弃" in result.sections_dropped


def test_priority_1_never_dropped() -> None:
    pb = PromptBuilder(budget=20)
    result = pb.build(
        [
            PromptSection("绝对必须", "x" * 500, priority=1),
            PromptSection("可压缩", "y" * 500, priority=3),
        ]
    )
    # 即使爆预算 priority=1 也保留(over_budget=True 警示)
    assert "绝对必须" in result.text


def test_truncation_preserves_header() -> None:
    pb = PromptBuilder(budget=50)
    long_content = "abcde fghij klmno pqrst uvwxy " * 50
    result = pb.build(
        [
            PromptSection("长段", long_content, priority=3),
        ]
    )
    # header "【长段】" 应保留,内容应被截断
    assert "【长段】" in result.text
    # 截断标记
    assert "…" in result.text or len(result.text) < len(long_content)


def test_count_tokens_basic() -> None:
    assert PromptBuilder.count_tokens("") == 0
    assert PromptBuilder.count_tokens("hello world") > 0


def test_header_and_footer_passed_through() -> None:
    pb = PromptBuilder(budget=2000)
    result = pb.build(
        [PromptSection("body", "section content", priority=3)],
        header="# System Header",
        footer="# Footer Notes",
    )
    assert "System Header" in result.text
    assert "Footer Notes" in result.text
    assert "section content" in result.text
