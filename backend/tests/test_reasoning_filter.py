from __future__ import annotations

from nf_core.reasoning_filter import strip_reasoning_leak
from quality_metrics.style_contract import style_contract_report


def test_strip_reasoning_leak_removes_standalone_markdown_language_tag() -> None:
    original = "林雪把信号弹收回腰间。\ntext\n苏莫扶墙站稳。"

    cleaned, leaked = strip_reasoning_leak(original)

    assert leaked is True
    assert cleaned == "林雪把信号弹收回腰间。\n苏莫扶墙站稳。"


def test_strip_reasoning_leak_keeps_inline_english_word() -> None:
    original = "屏幕上的 text 字段已经熄灭。"

    cleaned, leaked = strip_reasoning_leak(original)

    assert leaked is False
    assert cleaned == original


def test_style_contract_flags_standalone_wrapper_fragment() -> None:
    report = style_contract_report(
        "ensemble_epic",
        "林雪抬起枪。\nmarkdown\n苏莫推开门。",
        ("no_meta_leak",),
        strict=True,
    )

    assert report.requires_rewrite is True
    assert report.findings[0].code == "no_meta_leak"


def test_strip_and_detect_wrapper_prefix_glued_to_chinese() -> None:
    original = "林雪侧耳听。\nther她抽出探棒。"

    cleaned, leaked = strip_reasoning_leak(original)
    report = style_contract_report(
        "ensemble_epic", original, ("no_meta_leak",), strict=True
    )

    assert leaked is True
    assert cleaned == "林雪侧耳听。\n她抽出探棒。"
    assert report.requires_rewrite is True
