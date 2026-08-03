"""Deterministic, non-quoting feature extraction for user style samples.

The sample is measured locally and never copied into an anchor.  Returned
anchors contain only coarse structural classifications and aggregate counts,
so they are safe to include in a style prompt without reproducing user prose.
"""

from __future__ import annotations

import re


_SENTENCE_END_RE = re.compile(r"[。！？!?]+|…{1,2}")
_DIALOGUE_RE = re.compile(r"(?:“([^”]*)”|\"([^\"]*)\")", re.DOTALL)
_CLAUSE_PUNCTUATION_RE = re.compile(r"[，,、；;：:—…]")


def _non_whitespace_count(value: str) -> int:
    return sum(1 for character in value if not character.isspace())


def _band(value: float, *thresholds: tuple[float, str], fallback: str) -> str:
    for maximum, label in thresholds:
        if value <= maximum:
            return label
    return fallback


def derive_style_anchors(sample: str) -> list[str]:
    """Return aggregate style anchors without any source-text fragment."""

    text = str(sample or "")
    non_whitespace_chars = _non_whitespace_count(text)
    if non_whitespace_chars == 0:
        return []

    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    paragraph_count = max(1, len(paragraphs))
    sentence_endings = _SENTENCE_END_RE.findall(text)
    sentence_count = max(1, len(sentence_endings))
    average_sentence_chars = non_whitespace_chars / sentence_count
    average_paragraph_chars = non_whitespace_chars / paragraph_count

    dialogue_chars = 0
    for match in _DIALOGUE_RE.finditer(text):
        dialogue_chars += _non_whitespace_count(match.group(1) or match.group(2) or "")
    dialogue_ratio = min(1.0, dialogue_chars / non_whitespace_chars)

    clause_punctuation_count = len(_CLAUSE_PUNCTUATION_RE.findall(text))
    clause_marks_per_sentence = clause_punctuation_count / sentence_count

    sentence_band = _band(
        average_sentence_chars,
        (14.0, "短句倾向"),
        (28.0, "中等句长"),
        (45.0, "中长句倾向"),
        fallback="长句倾向",
    )
    paragraph_band = _band(
        average_paragraph_chars,
        (80.0, "留白较多的轻段落"),
        (180.0, "中等段落密度"),
        fallback="信息较密的长段落",
    )
    dialogue_band = _band(
        dialogue_ratio,
        (0.12, "低对话占比"),
        (0.38, "中等对话占比"),
        fallback="高对话占比",
    )
    rhythm_band = _band(
        clause_marks_per_sentence,
        (1.0, "停顿稀疏、推进直接"),
        (3.0, "长短停顿交替"),
        fallback="停顿密集、层次复合",
    )

    return [
        (
            f"句长特征：{sentence_band}（非空白字符 {non_whitespace_chars}，"
            f"句数 {sentence_count}，平均约 {average_sentence_chars:.1f} 字/句）"
        ),
        (
            f"段落特征：{paragraph_band}（段落数 {paragraph_count}，"
            f"平均约 {average_paragraph_chars:.1f} 字/段）"
        ),
        f"对话特征：{dialogue_band}（引号内字符占比约 {dialogue_ratio:.0%}）",
        (
            f"标点节奏：{rhythm_band}（分句标点约 "
            f"{clause_marks_per_sentence:.1f} 个/句）"
        ),
    ]


__all__ = ["derive_style_anchors"]
