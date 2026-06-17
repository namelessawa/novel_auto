"""Phase 6-C first slice — prose_dynamics tests.

Sentence rhythm (E1) + abstraction-density (D6) det checks. We don't try to
match the LLM critic's precision — these are *cheap pre-filters* for the det
layer. The bar is "no false trigger on real Phase 5-J narratives, clear
trigger on degenerate samples".

Real narrative samples cited inline are from `docs/iter/bench-phase5j-*` and
should remain stable as long as the bench data does (commit 82820a5 onward).
"""

from __future__ import annotations

import pytest

from quality_metrics.prose_dynamics import (
    ProseDynamicsReport,
    d6_abstraction_check,
    e1_rhythm_check,
    prose_dynamics_report,
    sentence_length_stats,
    split_sentences,
)


# A real Phase 5-J narrative sample. Healthy prose, varied sentence length.
_HEALTHY_SAMPLE = (
    "酸雨落了整夜。天亮时没停。"
    "铁影城的屋顶在雾中只露出轮廓, 像一排生锈的锯齿。"
    "街巷窄, 两面高墙夹着, 雨水沿墙根淌下来, 颜色发黄, "
    "碰到铁栏杆就嘶嘶响, 冒一点白烟。"
    "栏杆上原本有漆, 早被蚀光了, 露出底下坑洼的铸铁。"
    "玄烛低头走过赤铜巷。"
    "外套领子竖着, 还是挡不住那股味道 — 煤烟混铁锈, 呛嗓子。"
    "他把布袋换到另一边肩上, 里面的东西硌着肋骨。"
    "三份卷宗, 封蜡完好, 是昨夜从外城守备处领回来的。"
)

# A degenerate flat-rhythm sample. All sentences ~10 chars. Should trigger E1.
_FLAT_RHYTHM_SAMPLE = (
    "他走进房间。"
    "房间很安静。"
    "桌上有书本。"
    "他坐了下来。"
    "灯光不太亮。"
    "外面在下雨。"
    "他打开书页。"
    "字迹很潦草。"
)

# An abstraction-heavy sample. Big adjectives, no concrete props.
_ABSTRACT_SAMPLE = (
    "古老的城邦笼罩在神秘的氛围里, 宏伟的塔楼直插苍茫的天际, "
    "幽深的小巷弥漫着永恒的孤寂, 璀璨的星辰映照着浩瀚的过往, "
    "斑斓的色彩遮盖了凄美的回忆, 瑰丽的传说回响在亘古的钟声中。"
)

# A concrete sample. Lots of body parts + objects + materials.
_CONCRETE_SAMPLE = (
    "他抬手, 指尖蹭过桌沿的木刺, 一滴血落在纸上。刀鞘从腰间滑到膝边, "
    "杯里的酒晃了晃, 灯火被风吹得偏了一截, 门外石阶湿了, 雨水顺着窗框滴下来。"
)


# ---- sentence splitting ---------------------------------------------------


def test_split_sentences_basic():
    out = split_sentences("第一句。第二句!第三句?")
    assert out == ["第一句", "第二句", "第三句"]


def test_split_sentences_empty_input():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_split_sentences_drops_blanks_from_consecutive_punct():
    out = split_sentences("话。。。停顿。")
    assert out == ["话", "停顿"]


def test_split_sentences_ellipsis_treated_as_boundary():
    out = split_sentences("欲言又止…她转身。")
    assert out == ["欲言又止", "她转身"]


# ---- length stats ---------------------------------------------------------


def test_sentence_stats_empty_when_under_two_sentences():
    assert sentence_length_stats("一句话。") == {}
    assert sentence_length_stats("") == {}


def test_sentence_stats_computes_stddev():
    s = sentence_length_stats(_HEALTHY_SAMPLE)
    assert s["count"] >= 5
    assert 5.0 < s["mean"] < 50.0
    assert s["stddev"] > 0
    assert s["min"] < s["max"]


# ---- E1 sentence rhythm --------------------------------------------------


def test_e1_no_trigger_on_healthy_real_sample():
    triggered, evidence = e1_rhythm_check(_HEALTHY_SAMPLE)
    assert not triggered, f"healthy Phase 5-J sample triggered E1: {evidence}"


def test_e1_triggers_on_flat_rhythm():
    triggered, evidence = e1_rhythm_check(_FLAT_RHYTHM_SAMPLE)
    assert triggered
    assert "stddev=" in evidence
    assert "threshold" in evidence


def test_e1_no_trigger_on_short_paragraph():
    # 3 sentences — below the 5-sentence sanity guard
    short_text = "他来。她走。门关了。"
    triggered, _ = e1_rhythm_check(short_text)
    assert not triggered


def test_e1_custom_min_stddev_threshold():
    # Even healthy sample triggers if we crank threshold very high.
    triggered, _ = e1_rhythm_check(_HEALTHY_SAMPLE, min_stddev=99.0)
    assert triggered


# ---- D6 abstraction -----------------------------------------------------


def test_d6_triggers_on_pure_abstraction():
    triggered, evidence = d6_abstraction_check(_ABSTRACT_SAMPLE)
    assert triggered
    assert "abstract:concrete" in evidence
    assert "Top hits:" in evidence


def test_d6_no_trigger_on_concrete_sample():
    triggered, _ = d6_abstraction_check(_CONCRETE_SAMPLE)
    assert not triggered


def test_d6_no_trigger_on_healthy_real_sample():
    triggered, evidence = d6_abstraction_check(_HEALTHY_SAMPLE)
    assert not triggered, f"healthy sample triggered D6: {evidence}"


def test_d6_no_trigger_on_empty_or_neutral_text():
    assert d6_abstraction_check("")[0] is False
    # Text with neither abstract nor concrete words: total=0 → no trigger
    assert d6_abstraction_check("abc 123 这是一段")[0] is False


# ---- combined report -----------------------------------------------------


def test_report_healthy_sample_has_no_surviving_triggers():
    r = prose_dynamics_report(_HEALTHY_SAMPLE)
    assert isinstance(r, ProseDynamicsReport)
    assert r.surviving_triggers == []
    assert not r.e1_triggered
    assert not r.d6_triggered


def test_report_flat_rhythm_has_only_e1():
    r = prose_dynamics_report(_FLAT_RHYTHM_SAMPLE)
    assert r.surviving_triggers == ["E1"]
    assert r.e1_triggered
    assert not r.d6_triggered


def test_report_abstract_sample_has_only_d6():
    r = prose_dynamics_report(_ABSTRACT_SAMPLE)
    assert "D6" in r.surviving_triggers
    assert r.d6_triggered


def test_report_to_dict_preserves_structure():
    r = prose_dynamics_report(_FLAT_RHYTHM_SAMPLE)
    d = r.to_dict()
    assert d["e1"]["triggered"] is True
    assert d["d6"]["triggered"] is False
    assert d["sentence_stats"]
    assert d["surviving_triggers"] == ["E1"]


def test_report_empty_text_returns_no_triggers():
    r = prose_dynamics_report("")
    assert r.text_length == 0
    assert r.surviving_triggers == []
    assert r.sentence_stats == {}
