"""Prose diversity / vocabulary richness metrics — Phase 3-C extension.

Complementary to ``repetition`` n-gram view. Where ``distinct_char_n`` measures
n-gram uniqueness within a window, these metrics capture:

1. **Type-Token Ratio (TTR)** — classic lexical diversity. Unique characters
   (or words) divided by total. Range [0, 1]. Higher = richer vocabulary.
   * Note: TTR is sensitive to text length (longer texts trend lower); use
     normalized variants (MTTR, MATTR) for cross-length comparison.
2. **Mean / std sentence length** — sentence rhythm signal. Steady ~12-char
   sentences = monotone; high variance = dynamic prose.
3. **Mean word / char per sentence** — density signal.

Used to surface "narrator slim" (iter#114) style regressions where overlap
metrics fire but distinct-n doesn't (different aspect of repetition).

All functions are pure, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import mean, pstdev

from quality_metrics.repetition import _words

# iter#117 review MEDIUM: \n+ 含在 sentence-end 里 → 段落分割 (\n\n) 与
# 句号同等切. 真 bench 原稿常含 \n\n 段落, 此处当前实现会把段间当句界,
# 句数膨胀 / 平均句长偏低. Phase 3-C 首版可接受 (TTR/MATTR 不受影响),
# 后续 iter 升级 split 策略时同步更新此处.
_SENTENCE_END_RE = re.compile(r"[。！？!?\.\n]+")


def _sentences(text: str) -> list[str]:
    """切分中英文句子. 中英标点 + 换行作分隔."""
    if not text:
        return []
    parts = _SENTENCE_END_RE.split(text)
    return [s.strip() for s in parts if s and s.strip()]


def _chars(text: str) -> list[str]:
    """Char list (whitespace removed)."""
    return [c for c in text if not c.isspace()]


def type_token_ratio_char(text: str) -> float:
    """TTR on characters. 1.0 = all chars unique, 0.0 = empty text.

    Use case: detect 词汇贫乏 narrations 重复用同一批字.
    """
    chars = _chars(text)
    if not chars:
        return 0.0
    return len(set(chars)) / len(chars)


def type_token_ratio_word(text: str) -> float:
    """TTR on words (light-split). 词类丰富度."""
    words = _words(text)
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def mattr(text: str, window: int = 100) -> float:
    """Moving-Average TTR — 滑动窗口 TTR 均值, 长度无关化.

    每个 window-size 段算 TTR, 全部均值. Empty/短于 window 时回退到普通 TTR.
    """
    chars = _chars(text)
    if len(chars) < window:
        return type_token_ratio_char(text)
    ratios = []
    for i in range(len(chars) - window + 1):
        seg = chars[i : i + window]
        ratios.append(len(set(seg)) / window)
    return mean(ratios) if ratios else 0.0


def sentence_length_stats(text: str) -> tuple[float, float]:
    """返回 (均值, 总体标准差) of sentence char length.

    Empty → (0.0, 0.0). 单句 → (sentence_length, 0.0). 高 std = 长短交错;
    低 std = 节奏单调.
    """
    sentences = _sentences(text)
    if not sentences:
        return 0.0, 0.0
    lengths = [len(_chars(s)) for s in sentences]
    if len(lengths) < 2:
        return float(lengths[0]) if lengths else 0.0, 0.0
    return mean(lengths), pstdev(lengths)


@dataclass
class DiversityReport:
    """Bundled prose diversity view for a narration sequence.

    Per-narration metrics are averaged across the sequence. Sequence-empty
    yields all-zero report; check ``narration_count`` before drawing inferences.
    """

    narration_count: int = 0
    mean_ttr_char: float = 0.0
    mean_ttr_word: float = 0.0
    mean_mattr_100: float = 0.0  # length-normalised
    mean_sentence_length: float = 0.0
    mean_sentence_length_std: float = 0.0  # avg of per-narration sentence std

    def to_dict(self) -> dict:
        return {
            "narration_count": self.narration_count,
            "ttr": {
                "char": round(self.mean_ttr_char, 4),
                "word": round(self.mean_ttr_word, 4),
                "mattr_100": round(self.mean_mattr_100, 4),
            },
            "sentence_rhythm": {
                "mean_length": round(self.mean_sentence_length, 2),
                "mean_length_std": round(self.mean_sentence_length_std, 2),
            },
        }


def diversity_report(narrations: list[str]) -> DiversityReport:
    """Compute prose diversity over a sequence of narrations."""
    non_empty = [n for n in narrations if n and n.strip()]
    rep = DiversityReport(narration_count=len(non_empty))
    if not non_empty:
        return rep

    def _safe_mean(vals: list[float]) -> float:
        return mean(vals) if vals else 0.0

    rep.mean_ttr_char = _safe_mean([type_token_ratio_char(t) for t in non_empty])
    rep.mean_ttr_word = _safe_mean([type_token_ratio_word(t) for t in non_empty])
    rep.mean_mattr_100 = _safe_mean([mattr(t, 100) for t in non_empty])

    sent_stats = [sentence_length_stats(t) for t in non_empty]
    rep.mean_sentence_length = _safe_mean([m for m, _ in sent_stats])
    rep.mean_sentence_length_std = _safe_mean([s for _, s in sent_stats])

    return rep


__all__ = [
    "DiversityReport",
    "diversity_report",
    "mattr",
    "sentence_length_stats",
    "type_token_ratio_char",
    "type_token_ratio_word",
]
