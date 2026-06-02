"""Tests for CreativityScorer — 词汇 / 结构 / 情感多样性滑窗追踪。"""

from __future__ import annotations

import pytest

from narrative.creativity_scorer import (
    CreativityScorer,
    compute_metrics,
)


# ---------------------------------------------------------------------------
# compute_metrics — 确定性
# ---------------------------------------------------------------------------


def test_compute_metrics_empty_text() -> None:
    m = compute_metrics("")
    assert m.token_count == 0
    assert m.ttr == 0.0
    assert m.sentence_count == 0


def test_compute_metrics_basic() -> None:
    text = "他停在门口。雨开始下。她抬起头。"
    m = compute_metrics(text, tick=5)
    assert m.tick == 5
    assert m.token_count > 0
    assert m.sentence_count == 3
    assert 0.0 < m.ttr <= 1.0
    assert m.opening_signature.startswith("他停在")


def test_compute_metrics_detects_emotions() -> None:
    text = "她笑了。他怒火中烧。"
    m = compute_metrics(text)
    assert "joy" in m.emotional_categories
    assert "anger" in m.emotional_categories


def test_compute_metrics_low_ttr_for_repetition() -> None:
    # 大量重复 → TTR 低
    repetitive = "光光光光光光光光光光"
    m = compute_metrics(repetitive)
    assert m.ttr < 0.2


def test_compute_metrics_high_ttr_for_diverse() -> None:
    diverse = "他走过石阶看见远山的雪线在暮色里收紧"
    m = compute_metrics(diverse)
    assert m.ttr > 0.8


# ---------------------------------------------------------------------------
# CreativityScorer — 滑窗 + 基线
# ---------------------------------------------------------------------------


def test_scorer_baseline_locks_after_n() -> None:
    scorer = CreativityScorer(window_size=5, baseline_size=8)
    for i in range(7):
        scorer.ingest_paragraph(f"段落{i} 内容 文本 这里 是 {i}", tick=i)
    assert scorer.baseline_locked is False
    scorer.ingest_paragraph("最后一段 触发 基线 锁定", tick=8)
    assert scorer.baseline_locked is True


def test_scorer_report_before_lock_is_empty() -> None:
    scorer = CreativityScorer(window_size=5, baseline_size=10)
    scorer.ingest_paragraph("第一段", tick=0)
    rep = scorer.report()
    assert rep.summary == "尚未锁定基线"
    assert rep.alerts == []


def test_scorer_alerts_on_lex_degeneration() -> None:
    """前 20 段词汇丰富, 后 10 段全重复 — 应触发 CRX_LEX。"""
    scorer = CreativityScorer(window_size=10, baseline_size=20)
    diverse_pool = [
        "石阶上落着潮湿的苔藓他踩过去",
        "灯塔旁的雾在夜里慢慢散去",
        "钟声从远方传来打破水面的镜面",
        "她的手指划过窗台留下指纹",
        "晨光照在锈迹斑斑的铁门上",
        "院子里的老树折下一根枝",
        "远处的炊烟卷成细密的纹路",
        "山涧的水声夹杂着鸟鸣",
        "海上的浪头拍碎了月亮",
        "雪在屋檐边缘悄悄堆积",
    ]
    # 基线: 20 段词汇丰富
    for i in range(20):
        scorer.ingest_paragraph(diverse_pool[i % len(diverse_pool)], tick=i)
    # 窗口: 10 段几乎相同
    for i in range(10):
        scorer.ingest_paragraph("他走他走他走他走他走", tick=20 + i)
    rep = scorer.report()
    codes = {a.code for a in rep.alerts}
    assert "CRX_LEX" in codes


def test_scorer_alerts_on_emo_degeneration() -> None:
    """前 20 段情感丰富, 后 10 段全无情感词 — 应触发 CRX_EMO。"""
    scorer = CreativityScorer(window_size=10, baseline_size=20)
    diverse_emos = [
        "她笑了起来",
        "他愤怒地推开门",
        "孩子哭着跑出去",
        "众人惊讶地后退",
        "院子里很静很静",
    ]
    for i in range(20):
        scorer.ingest_paragraph(diverse_emos[i % len(diverse_emos)], tick=i)
    # 窗口: 10 段全部无情感
    for i in range(10):
        scorer.ingest_paragraph("石头", tick=20 + i)
    rep = scorer.report()
    codes = {a.code for a in rep.alerts}
    assert "CRX_EMO" in codes


def test_scorer_no_alert_when_stable() -> None:
    scorer = CreativityScorer(window_size=5, baseline_size=10)
    pool = [
        "他停在门口看窗外",
        "她转身离开了大厅",
        "雨开始下风声紧",
        "灯塔的光闪了一下",
        "海浪撞在岩石上",
    ]
    # 基线和窗口同样多样化 — 不应触发
    for i in range(15):
        scorer.ingest_paragraph(pool[i % len(pool)], tick=i)
    rep = scorer.report()
    assert rep.alerts == [] or all(a.severity != "high" for a in rep.alerts)


def test_scorer_report_dict_serializable() -> None:
    scorer = CreativityScorer(window_size=3, baseline_size=5)
    for i in range(8):
        scorer.ingest_paragraph(f"段落 {i} 文本", tick=i)
    d = scorer.report().to_dict()
    assert "paragraph_count" in d
    assert "alerts" in d
    assert isinstance(d["alerts"], list)


def test_scorer_history_bounded() -> None:
    """长跑场景: history 不应无限增长。"""
    scorer = CreativityScorer(window_size=5, baseline_size=10)
    for i in range(200):
        scorer.ingest_paragraph(f"段{i}", tick=i)
    assert scorer.history_size <= 15  # baseline + window


def test_scorer_alert_drop_pct_in_range() -> None:
    """drop_pct 在 [0, 1] 之间, 不出负值。"""
    scorer = CreativityScorer(window_size=5, baseline_size=10)
    for i in range(10):
        scorer.ingest_paragraph("丰富的多样的语言变化", tick=i)
    for i in range(5):
        scorer.ingest_paragraph("同同同同同同同同", tick=10 + i)
    rep = scorer.report()
    for a in rep.alerts:
        assert 0.0 <= a.drop_pct <= 1.0
