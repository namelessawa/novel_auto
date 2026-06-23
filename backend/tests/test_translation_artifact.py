"""Phase 6-C 第四刀 — translation_artifact tests (E7).

iter#3 加的 quality_metrics/translation_artifact.py 模块. 之前只通过
quality_checks wrapper 集成测试. 这里补 internal API edge cases:

* per-pattern detection (7 patterns)
* min_hits guard (default=2, custom)
* TranslationArtifactReport to_dict
* empty / no-hit / single-hit 边界
"""

from __future__ import annotations

from quality_metrics.translation_artifact import (
    TranslationArtifactReport,
    e7_translation_artifact_check,
    translation_artifact_report,
)


# Healthy 长程段落 — 无翻译腔 pattern.
_HEALTHY_SAMPLE = (
    "灰钢往下走。每走一步,鞋底的油膜就发出吱嘎声。"
    "阶梯很长,比她预想的深。墙壁上的铜管越来越密。"
    "铁门没锁。门轴转动时发出的是低沉的嗡鸣。"
    "灰钢伸手去碰。指尖离表面还有一寸时,玻璃亮了。"
)

# 7 种 pattern 都有的 degenerate 样本.
_HEAVY_SAMPLE = (
    "对于这件事来说,这是一个无法解释的现象。"
    "对于她而言,被命运所束缚的感觉从未消失。"
    "由于过去十年的原因,她的眼睛变成了纸。"
    "不仅这是一个荒诞的事实,而且也是一种无法逃避的真相。"
    "这是一个让人无法接受的事实。"
    "他的疲惫的沉重的灰白的眼神。"
)


# ---- per-pattern detection ------------------------------------------------


def test_对于来说_pattern_detected() -> None:
    triggered, _, hits = e7_translation_artifact_check(
        "对于他来说,这件事并不重要。对于她来说,这是一切。"
    )
    assert "对于…来说" in hits
    assert hits["对于…来说"] == 2
    assert triggered


def test_这是一个的_pattern_detected() -> None:
    triggered, _, hits = e7_translation_artifact_check(
        "这是一个深沉的人。这是一个安静的夜。"
    )
    assert "这是一个…的" in hits
    assert hits["这是一个…的"] == 2
    assert triggered


def test_被所_pattern_detected() -> None:
    triggered, _, hits = e7_translation_artifact_check(
        "他被命运所束缚。她被时间所改变。"
    )
    assert "被…所…" in hits
    assert triggered


def test_long_de_chain_pattern_detected() -> None:
    """3+ '的' 连缀 pattern."""
    text = "他的疲惫的沉重的灰白的眼神。她的苍白的瘦削的脸。"
    triggered, _, hits = e7_translation_artifact_check(text)
    assert "长定语链" in hits
    assert triggered


def test_不仅而且_pattern_detected() -> None:
    triggered, _, hits = e7_translation_artifact_check(
        "他不仅累了,而且饿了。她不仅迷茫,而且无助。"
    )
    assert "不仅…而且…" in hits
    assert triggered


def test_由于的原因_pattern_detected() -> None:
    triggered, _, hits = e7_translation_artifact_check(
        "由于过去的原因,他离开了。由于战争的原因,城市消失了。"
    )
    assert "由于…的原因" in hits
    assert triggered


def test_对而言_pattern_detected() -> None:
    triggered, _, hits = e7_translation_artifact_check(
        "对他而言,这是新生。对她而言,这是终结。"
    )
    assert "对…而言" in hits
    assert triggered


# ---- min_hits guard -----------------------------------------------------


def test_single_pattern_hit_below_default_threshold() -> None:
    """单 pattern 单次 hit < min_hits(2) → 不触发."""
    triggered, _, hits = e7_translation_artifact_check(
        "对于他来说这并不算什么。后面就是动作和场景描写。"
    )
    assert hits.get("对于…来说") == 1
    assert not triggered


def test_two_different_patterns_each_once_triggers() -> None:
    """两种 pattern 各 1 次, total=2 → 触发."""
    triggered, evidence, _ = e7_translation_artifact_check(
        "对于他来说这是一个新的开始。"
    )
    assert triggered
    assert "Top:" in evidence


def test_custom_min_hits_threshold() -> None:
    """提高 min_hits=5 — heavy 样本依然触发."""
    triggered, _, _ = e7_translation_artifact_check(_HEAVY_SAMPLE, min_hits=5)
    assert triggered
    # min_hits=20 — heavy 也不触发 (no sample 有 20 hits)
    triggered_high, _, _ = e7_translation_artifact_check(
        _HEAVY_SAMPLE, min_hits=200
    )
    assert not triggered_high


# ---- empty / no-hit ------------------------------------------------------


def test_empty_text_no_trigger() -> None:
    triggered, evidence, hits = e7_translation_artifact_check("")
    assert not triggered
    assert evidence == ""
    assert hits == {}


def test_healthy_real_sample_no_trigger() -> None:
    triggered, _, hits = e7_translation_artifact_check(_HEALTHY_SAMPLE)
    assert not triggered, f"healthy sample triggered E7: hits={hits}"


# ---- combined report ----------------------------------------------------


def test_report_healthy_sample_no_trigger() -> None:
    r = translation_artifact_report(_HEALTHY_SAMPLE)
    assert isinstance(r, TranslationArtifactReport)
    assert not r.e7_triggered
    assert r.total_hits <= 1  # 偶有 isolated single-hit


def test_report_heavy_sample_triggers_with_evidence() -> None:
    r = translation_artifact_report(_HEAVY_SAMPLE)
    assert r.e7_triggered
    assert r.total_hits >= 2
    assert "Top:" in r.e7_evidence


def test_report_to_dict_structure() -> None:
    r = translation_artifact_report(_HEAVY_SAMPLE)
    d = r.to_dict()
    assert d["e7"]["triggered"] is True
    assert "pattern_hits" in d
    assert "total_hits" in d
    assert isinstance(d["pattern_hits"], dict)


def test_report_empty_text_safe_default() -> None:
    r = translation_artifact_report("")
    assert r.text_length == 0
    assert r.total_hits == 0
    assert not r.e7_triggered
