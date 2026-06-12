"""iter#116 Phase 3-C — quality_metrics/diversity.py tests."""

from __future__ import annotations

import pytest

from quality_metrics.diversity import (
    DiversityReport,
    diversity_report,
    mattr,
    sentence_length_stats,
    type_token_ratio_char,
    type_token_ratio_word,
)


# --- TTR char ---------------------------------------------------------------


def test_ttr_char_empty_returns_zero():
    assert type_token_ratio_char("") == 0.0


def test_ttr_char_all_unique():
    """5 个不同字符 → TTR = 1.0."""
    assert type_token_ratio_char("abcde") == 1.0


def test_ttr_char_all_same():
    """5 个相同字符 → TTR = 1/5 = 0.2."""
    assert type_token_ratio_char("aaaaa") == 0.2


def test_ttr_char_ignores_whitespace():
    """Whitespace 不计入字符总数."""
    assert type_token_ratio_char("a b c") == type_token_ratio_char("abc")


def test_ttr_char_chinese():
    """中文 5 字全异 → 1.0; 重复 5 字 → 0.2."""
    assert type_token_ratio_char("一二三四五") == 1.0
    assert type_token_ratio_char("一一一一一") == 0.2


# --- TTR word ---------------------------------------------------------------


def test_ttr_word_empty():
    assert type_token_ratio_word("") == 0.0


def test_ttr_word_punctuation_split():
    """汉语标点分词 — '他来了。她走了。' = 2 token (无重复)."""
    assert type_token_ratio_word("他来了。她走了。") == 1.0


def test_ttr_word_repeated():
    """重复同 token → 比 1.0 小."""
    text = "他来了。他来了。他来了。"
    ttr = type_token_ratio_word(text)
    assert 0 < ttr < 1.0


# --- MATTR ------------------------------------------------------------------


def test_mattr_short_text_falls_back_to_ttr():
    """文本 < window → 回退普通 TTR."""
    text = "abcdef"  # 6 < 100
    assert mattr(text, window=100) == type_token_ratio_char(text)


def test_mattr_long_text_uses_window():
    """长文本 → 滑窗均值, 不简单退化."""
    # 200 字符, 全异 → window-TTR = window 字符全异概率, 应 = 1.0
    text = "".join(chr(0x4E00 + i) for i in range(200))  # 200 个不同汉字
    assert mattr(text, window=100) == 1.0


def test_mattr_window_with_repeats():
    """100 字符里 50 unique → window-TTR = 0.5."""
    chars_a = "".join(chr(0x4E00 + i) for i in range(50))
    text = chars_a * 2  # 100 字符, 50 unique
    val = mattr(text, window=100)
    assert val == 0.5


# --- sentence length stats --------------------------------------------------


def test_sentence_length_empty():
    assert sentence_length_stats("") == (0.0, 0.0)


def test_sentence_length_single_sentence():
    """单句 → mean=length, std=0."""
    mean, std = sentence_length_stats("他来了一个人")
    assert mean == 6
    assert std == 0.0


def test_sentence_length_two_sentences():
    """两句 → mean & std 非零."""
    text = "abc。abcdef。"  # 3 字符 + 6 字符
    mean, std = sentence_length_stats(text)
    assert mean == 4.5
    assert std > 0


def test_sentence_length_monotone():
    """完全相同长度的句子 → std=0 (节奏单调)."""
    text = "abc。def。ghi。"
    _, std = sentence_length_stats(text)
    assert std == 0.0


# --- DiversityReport --------------------------------------------------------


def test_diversity_report_empty():
    rep = diversity_report([])
    assert rep.narration_count == 0
    assert rep.mean_ttr_char == 0.0


def test_diversity_report_skips_empty_narrations():
    """空 narration 不计入."""
    rep = diversity_report(["abc", "", "  ", "def"])
    assert rep.narration_count == 2


def test_diversity_report_to_dict_schema():
    """to_dict 必含 ttr 和 sentence_rhythm 二级 key."""
    rep = diversity_report(["abc。def。", "ghi。jkl。"])
    d = rep.to_dict()
    assert "ttr" in d
    assert "sentence_rhythm" in d
    assert {"char", "word", "mattr_100"} <= set(d["ttr"].keys())
    assert {"mean_length", "mean_length_std"} <= set(d["sentence_rhythm"].keys())


def test_diversity_report_mean_across_narrations():
    """每段 TTR=1 → 整体 mean=1.0."""
    rep = diversity_report(["abc", "def"])
    assert rep.mean_ttr_char == 1.0
