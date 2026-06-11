"""Tests for quality_metrics.repetition (Phase 2 Stage 0 — iter#76).

锁定 det 层 repetition 指标的语义, 防止后续 iter 误改公式让 Phase 2 全
部结论作废 (§2 工作规则 #5 — 指标本身错了, 后面全部结论作废).
"""

from __future__ import annotations

import pytest

from quality_metrics.repetition import (
    RepetitionReport,
    char_ngram_distinct,
    char_ngram_overlap,
    repetition_report,
    word_ngram_distinct,
    word_ngram_overlap,
)


# ---------------------------------------------------------------------------
# char-level n-gram
# ---------------------------------------------------------------------------


def test_char_distinct_all_unique() -> None:
    # "abcd" 2-gram: ab, bc, cd → 3 distinct / 3 total
    assert char_ngram_distinct("abcd", 2) == 1.0


def test_char_distinct_all_same() -> None:
    # "aaaa" 2-gram: aa, aa, aa → 1 distinct / 3 total = 1/3
    assert char_ngram_distinct("aaaa", 2) == pytest.approx(1 / 3)


def test_char_distinct_empty() -> None:
    assert char_ngram_distinct("", 2) == 0.0
    assert char_ngram_distinct("a", 2) == 0.0  # 单字 < n


def test_char_distinct_strips_whitespace() -> None:
    # "ab cd" with whitespace strip → "abcd", 同 test_char_distinct_all_unique
    assert char_ngram_distinct("ab cd", 2) == 1.0
    assert char_ngram_distinct("a\nb\ncd", 2) == 1.0


def test_char_ngram_overlap_identical() -> None:
    assert char_ngram_overlap("abcdef", "abcdef", 3) == 1.0


def test_char_ngram_overlap_disjoint() -> None:
    assert char_ngram_overlap("abcdef", "xyzwvu", 3) == 0.0


def test_char_ngram_overlap_partial() -> None:
    # "abcd": {ab,bc,cd}; "bcde": {bc,cd,de}
    # 交集 {bc,cd}=2, 并集 {ab,bc,cd,de}=4 → 0.5
    assert char_ngram_overlap("abcd", "bcde", 2) == 0.5


def test_char_ngram_overlap_empty_returns_zero() -> None:
    assert char_ngram_overlap("", "abc", 2) == 0.0
    assert char_ngram_overlap("abc", "", 2) == 0.0


def test_char_ngram_handles_chinese() -> None:
    text = "他低头走过赤铜巷。外套领子竖着。"
    grams = ["他低", "低头", "头走"]  # 部分预期 2-gram
    # 不直接调内部函数, 用 distinct 间接验证: 文本长度 13 (去标点), 2-gram 共
    # 12 个, 全 unique → distinct=1.0
    assert char_ngram_distinct(text, 2) == 1.0


# ---------------------------------------------------------------------------
# word-level n-gram
# ---------------------------------------------------------------------------


def test_word_distinct_all_unique() -> None:
    assert word_ngram_distinct("the quick brown fox", 2) == 1.0


def test_word_distinct_all_same() -> None:
    # "the the the the": 2-gram = "the the" × 3 → 1 distinct / 3
    assert word_ngram_distinct("the the the the", 2) == pytest.approx(1 / 3)


def test_word_ngram_handles_chinese_punctuation() -> None:
    # "他笑了。她也笑了。" 按中文标点切 → ["他笑了", "她也笑了"]
    # 1-gram: 2 unique / 2 total → 1.0
    assert word_ngram_distinct("他笑了。她也笑了。", 1) == 1.0


# ---------------------------------------------------------------------------
# RepetitionReport
# ---------------------------------------------------------------------------


def test_report_empty_input() -> None:
    rep = repetition_report([])
    assert rep.narration_count == 0
    assert rep.distinct_char_2 == 0.0
    assert rep.overlap_char_2_consecutive == 0.0


def test_report_single_narration_notes_no_overlap() -> None:
    rep = repetition_report(["他低头走过赤铜巷。"])
    assert rep.narration_count == 1
    assert "only_one_narration_no_overlap" in rep.notes
    assert rep.overlap_char_2_consecutive == 0.0
    assert rep.distinct_char_2 > 0


def test_report_counts_skipped_empties() -> None:
    rep = repetition_report(["第一段。", "", "  ", "第二段。"])
    assert rep.narration_count == 2
    assert any("skipped_empty_narrations=2" in n for n in rep.notes)


def test_report_high_overlap_signals_repetition() -> None:
    # 两段几乎相同 → consecutive overlap 应该非常高
    rep = repetition_report(
        ["他走过雨夜的街道, 雨水沿着屋檐滑落。", "他走过雨夜的街道, 雨水沿着屋顶滑落。"]
    )
    assert rep.narration_count == 2
    assert rep.overlap_char_2_consecutive > 0.5
    assert rep.overlap_char_3_consecutive > 0.5


def test_report_disjoint_narrations_low_overlap() -> None:
    rep = repetition_report(
        [
            "沈铁心把外套领子拢了拢, 雨从屋檐滴下来。",
            "苏默蹲在档案馆深处, 灯焰跳了两下。",
        ]
    )
    assert rep.narration_count == 2
    # 字符 overlap 应当较低 (毕竟换了人物和场景)
    assert rep.overlap_char_4_consecutive < 0.15


def test_report_to_dict_schema() -> None:
    rep = repetition_report(["第一段。", "第二段。"])
    d = rep.to_dict()
    assert d["narration_count"] == 2
    assert "char_2" in d["distinct"]
    assert "char_4" in d["distinct"]
    assert "word_2" in d["distinct"]
    assert "char_2" in d["overlap_consecutive"]
    assert isinstance(d["notes"], list)
    # 所有数字字段都是已 round 的 float
    for v in d["distinct"].values():
        assert isinstance(v, float)
    for v in d["overlap_consecutive"].values():
        assert isinstance(v, float)


def test_report_dataclass_roundtrip_stable() -> None:
    """同输入两次调用结果必须 bit-identical (deterministic 必须保证)."""
    seq = ["他笑了。", "她哭了。", "雨停了。"]
    a = repetition_report(seq).to_dict()
    b = repetition_report(seq).to_dict()
    assert a == b
