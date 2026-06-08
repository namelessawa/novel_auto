"""v2.33 — 文本分段器单测."""
from __future__ import annotations

from nf_core.text_segmenter import (
    HARD_MAX_CHARS,
    MAX_SEGMENT_CHARS,
    MIN_SEGMENT_CHARS,
    Segment,
    segment_text,
)


def _total_chars(segs: list[Segment]) -> int:
    return sum(s.char_count for s in segs)


def test_empty_input_returns_empty():
    assert segment_text("") == []
    assert segment_text("   \n\n  ") == []


def test_single_short_sentence():
    text = "晚风吹过山岗。"
    segs = segment_text(text)
    assert len(segs) == 1
    assert "晚风吹过山岗" in segs[0].text


def test_multiple_sentences_split_on_period():
    text = (
        "雪山下的村落在黄昏中显得格外宁静。月亮缓缓升起, 照亮了远方的小路。"
        "孩子们在田野里奔跑, 笑声传遍山谷。"
    )
    segs = segment_text(text)
    assert len(segs) >= 2
    # 每段都应该有合理长度
    for s in segs:
        assert s.char_count >= 1


def test_segments_dont_lose_content():
    text = "第一句。第二句!第三句?第四句, 但有逗号。"
    segs = segment_text(text)
    joined = "".join(s.text for s in segs)
    # 拼接后 (跳过空白) 应等于原文 (跳过空白)
    assert "".join(c for c in joined if not c.isspace()) == "".join(
        c for c in text if not c.isspace()
    )


def test_long_sentence_split_by_secondary():
    # 一句长达 200 字, 没有句号但有逗号 — 应该被切
    long_sent = "他想起小时候在山里跑过的那条溪流, 溪水清凉, 鱼儿成群, " * 5 + "。"
    segs = segment_text(long_sent)
    assert len(segs) >= 2
    for s in segs:
        assert s.char_count <= HARD_MAX_CHARS + 5  # 允许略超 (合并兜底)


def test_no_punctuation_hard_split():
    # 极端: 一行没有标点的超长串 — 强制硬切
    runaway = "啊" * 300
    segs = segment_text(runaway)
    assert len(segs) >= 2
    for s in segs:
        assert s.char_count <= HARD_MAX_CHARS + 5


def test_merge_short_neighbours():
    # 多个极短句 — 应该被合并
    text = "哦。是。好。来。走。停。看。说。听。"
    segs = segment_text(text)
    # 9 个 1 字句应该被合并成 1-2 段 (合并上限 MAX=60)
    assert len(segs) <= 2


def test_short_tail_merged_to_previous():
    # 末尾一个超短碎片 (< TAIL_FRAGMENT_CHARS) — 应反并到上一段
    text = "夜晚的森林安静得让人不安, 只有远处偶尔传来枭鸟的叫声。是。"
    segs = segment_text(text)
    # 不应该出现一个孤立的 "是。" — 末段一定不是 1-2 字碎片
    assert segs[-1].char_count >= 8


def test_segment_indices_are_sequential():
    text = "甲。乙。丙。丁。戊。" * 8
    segs = segment_text(text)
    for i, s in enumerate(segs):
        assert s.index == i


def test_newlines_treated_as_terminators():
    text = "第一段开头\n第二段开头\n第三段结尾。"
    segs = segment_text(text)
    # 至少能切出片段
    assert len(segs) >= 1


def test_target_length_not_too_short():
    # 一段适中的小说节 — 切完后段长应该在 MIN-MAX 范围
    paragraph = (
        "他推开窗户, 春风扑面而来。远处的山峦在朝阳下泛着金色, 像一幅未干的油画。"
        "院子里的桃树已经开花, 粉白的花瓣在微风中轻轻摇曳。"
        "他想起了童年的春天, 那时候母亲总在桃树下纳鞋底, 阳光把她的影子拉得很长。"
        "时间过得真快啊, 转眼间已经过去二十年了。"
    )
    segs = segment_text(paragraph)
    assert len(segs) >= 3  # 这种长度至少切 3 段
    avg = _total_chars(segs) / max(1, len(segs))
    # 平均段长应该接近 TARGET (15-50 都算合理)
    assert avg >= 10
    assert avg <= MAX_SEGMENT_CHARS
