"""Phase 6-C 第三刀 — character_signal tests (B4 inner-monologue ratio).

iter#1 加的 quality_metrics/character_signal.py 模块. 之前只通过
quality_checks wrapper 集成测试. 这里补 internal API edge cases:

* dialogue/inner counting under each quote style
* three guards (min_inner / min_ratio / vs dialogue or non-inner)
* CharacterSignalReport to_dict structure
* empty / short / all-quote / all-monologue 边界
"""

from __future__ import annotations

from quality_metrics.character_signal import (
    CharacterSignalReport,
    b4_inner_monologue_check,
    character_signal_report,
    count_dialogue_chars,
    count_inner_monologue_chars,
    count_total_cjk_chars,
)


# Real phase6a2 长程样本 — healthy 动作 + 对话, 几乎无内心独白.
_HEALTHY_SAMPLE = (
    "灰钢往下走。每走一步,鞋底的油膜就发出吱嘎声。"
    "\"地下三层。\"灰钢说。林雪没应。她的纸脸转向走廊尽头。"
    "铁门没锁。门轴转动时发出的是低沉的嗡鸣。"
)

# 全段内心独白堆积 — B4 设计意图捕获的 LLM 退化模式. dialogue=0.
_INNER_HEAVY_SAMPLE = (
    "他心想这一切究竟意味着什么,是命运的玩笑还是早已注定的结局。"
    "她暗忖自己是否还有退路,脑海中浮现出无数可能的未来。"
    "他想到母亲临终前的眼神,意识到自己从未真正理解她的选择。"
    "她回忆起那个雪夜,脑子里反复回放着两人最后一次对话的每一个字。"
    "他默念着祖父留下的训诫,心中暗暗发誓要走完这条路。"
    "她想道,或许真相比她预想的还要残酷。"
)

# 对话密集 — 即使含少量内心 marker, B4 不应触发.
_DIALOGUE_HEAVY_SAMPLE = (
    "\"你确定?\"他问,语气里有不易察觉的疲惫。"
    "\"位置无误。坐标是档案馆给的,他们不会出错。\"她回答得很快。"
    "\"那就走吧。\"他推开门。"
    "她跟在后面。\"小心脚下。\"他低声说,\"这里的地板有破洞。\""
)


# ---- char counters --------------------------------------------------------


def test_count_total_cjk_chars_empty() -> None:
    assert count_total_cjk_chars("") == 0
    assert count_total_cjk_chars("   ") == 0


def test_count_total_cjk_chars_pure_chinese() -> None:
    assert count_total_cjk_chars("一二三四五") == 5


def test_count_total_cjk_chars_excludes_punct_and_latin() -> None:
    """混合标点 / 拉丁字母 — 只计 CJK."""
    assert count_total_cjk_chars("Hello, 世界! 123 你好") == 4


def test_count_dialogue_chars_chinese_full_width_quotes() -> None:
    """中文全角引号 “...” 内字符正确计数."""
    assert count_dialogue_chars("他说“你好世界”然后走了。") == 4


def test_count_dialogue_chars_straight_quotes() -> None:
    assert count_dialogue_chars('他说"你好"。') == 2


def test_count_dialogue_chars_corner_brackets() -> None:
    """日式角引号 「」 也算 dialogue."""
    assert count_dialogue_chars("他说「再见」。") == 2


def test_count_dialogue_chars_empty_quote_payload() -> None:
    """空引号 \"\" 不算 dialogue char."""
    assert count_dialogue_chars('他说""然后转身。') == 0


def test_count_dialogue_chars_multiple_quotes() -> None:
    """多对引号字符数相加."""
    assert count_dialogue_chars('"一二""三四五"') == 5


# ---- inner monologue counter ---------------------------------------------


def test_count_inner_chars_no_marker() -> None:
    """无 marker → 0 chars, 0 snippets."""
    n, snippets = count_inner_monologue_chars("他走进房间。桌上有书本。")
    assert n == 0
    assert snippets == []


def test_count_inner_chars_marker_outside_quote_counted() -> None:
    """引号外的"想到 X" 整句计为 inner."""
    text = "他想到了一件事,是关于母亲的。"
    n, snippets = count_inner_monologue_chars(text)
    assert n > 0
    assert snippets and "想到" in snippets[0]


def test_count_inner_chars_marker_inside_quote_skipped() -> None:
    """引号内 marker 视为对白, 不计 inner."""
    text = '他大声说:"我想到了一件事!"然后跑出门。'
    n, _ = count_inner_monologue_chars(text)
    # "我想到了一件事!" 在引号里 → 跳过. 整段无引号外 marker → 0.
    assert n == 0


def test_count_inner_chars_evidence_capped_at_three() -> None:
    """超过 3 句含 marker → 只取前 3 个 snippets."""
    text = (
        "他心想一件事。她暗忖第二件。他想到第三件。"
        "她回忆起第四件。他意识到第五件。"
    )
    _, snippets = count_inner_monologue_chars(text)
    assert len(snippets) == 3


# ---- B4 trigger guards ---------------------------------------------------


def test_b4_no_trigger_on_short_inner() -> None:
    """inner_chars < min_inner_chars (60) → 即使 ratio 高也不触发."""
    text = "他心想这件事。"  # ~8 chars inner
    triggered, _, _ = b4_inner_monologue_check(text)
    assert not triggered


def test_b4_no_trigger_below_ratio_floor() -> None:
    """inner ≥ 60 但 inner/cjk < 0.40 → 不触发."""
    # 60 字 inner + 240 字 action = 300 总, inner/cjk = 0.20
    inner = "他心想一件事关于过去的事情,是母亲临终前没说完的那句话的真正含义。"
    action = (
        "他走出房间。雨已经下了一夜。屋檐还在滴水。他低头看了看鞋面"
        "已经湿透了。街灯还亮着。远处传来一声犬吠。他把外套裹紧。"
        "刀柄在腰间硌着肋骨。他不再回头,加快了脚步。"
    )
    text = inner + action
    triggered, _, _ = b4_inner_monologue_check(text)
    assert not triggered


def test_b4_triggers_on_all_inner_no_dialogue() -> None:
    """全段 inner + 0 dialogue → fallback 比较, remainder=0 直接触发."""
    triggered, evidence, _ = b4_inner_monologue_check(_INNER_HEAVY_SAMPLE)
    assert triggered
    assert "non-inner=0" in evidence or "dialogue=0" in evidence


def test_b4_no_trigger_when_dialogue_dominates() -> None:
    """dialogue >> inner → 不触发 (inner ≤ dialogue × 1.5)."""
    triggered, _, _ = b4_inner_monologue_check(_DIALOGUE_HEAVY_SAMPLE)
    assert not triggered


def test_b4_custom_ratio_threshold() -> None:
    """放宽 ratio_to_dialogue 到 0.5 — _INNER_HEAVY 仍触发 (dialogue=0)."""
    triggered, _, _ = b4_inner_monologue_check(
        _INNER_HEAVY_SAMPLE, ratio_to_dialogue=0.5
    )
    assert triggered


# ---- character_signal_report --------------------------------------------


def test_report_healthy_sample_no_trigger() -> None:
    r = character_signal_report(_HEALTHY_SAMPLE)
    assert isinstance(r, CharacterSignalReport)
    assert not r.b4_triggered
    assert r.b4_evidence == ""


def test_report_inner_heavy_triggers_b4() -> None:
    r = character_signal_report(_INNER_HEAVY_SAMPLE)
    assert r.b4_triggered
    assert r.inner_monologue_chars > 0
    assert r.dialogue_chars == 0


def test_report_to_dict_structure() -> None:
    r = character_signal_report(_INNER_HEAVY_SAMPLE)
    d = r.to_dict()
    assert d["b4"]["triggered"] is True
    assert "cjk_chars" in d
    assert "dialogue_chars" in d
    assert "inner_monologue_chars" in d
    assert "snippets" in d
    assert isinstance(d["snippets"], list)


def test_report_empty_text_safe_default() -> None:
    """空文本 — 不抛, 返回零值 report."""
    r = character_signal_report("")
    assert r.text_length == 0
    assert r.cjk_chars == 0
    assert not r.b4_triggered
