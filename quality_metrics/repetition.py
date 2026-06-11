"""Repetition / lexical diversity metrics for narrative text.

Two independent views, both reported (Phase 2 §3.1 mandate — 中文需分词或按
字符 n-gram, 二者都实现并分列):

1. **Character n-gram view** — robust to tokenisation choice, captures
   short-range reuse independent of word boundaries. Good for catching
   Chinese reuse of 2-4 字 phrasings.
2. **Word n-gram view** — uses a light segmenter (whitespace + punctuation
   split, with optional jieba upgrade later). Captures phrase-level reuse
   that escapes the char view when 2-char fragments don't align.

Two angles, both reported:

* **distinct-n** — type/token ratio over n-grams of a single text. Higher
  is better (vocabulary diversity).
* **overlap** — Jaccard overlap of n-gram sets between two texts.
  Cross-tick repetition signal: high overlap between adjacent narrations
  means the model is reusing phrasings.

The functions are pure (no I/O, no randomness). All counts are explicit;
no implicit thresholds — callers (bench writer) decide what "bad" looks
like.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_WORD_SPLIT_RE = re.compile(r"[\s　，。、；：！？“”‘’（）《》【】「」『』·、—…\.\,\;\:\!\?\"'\(\)\[\]\{\}]+")


def _char_ngrams(text: str, n: int) -> list[str]:
    """Char-level n-gram list. Whitespace 和换行被剔除前先 normalize,
    防止行间偶尔的 '\n\n' 把同一句话的两端撕成不同 token.

    返回 list 而非 set, 让 distinct-n 能区分总数 vs 唯一数.
    """
    if n < 1 or not text:
        return []
    cleaned = re.sub(r"\s+", "", text)
    if len(cleaned) < n:
        return []
    return [cleaned[i : i + n] for i in range(len(cleaned) - n + 1)]


def _words(text: str) -> list[str]:
    """轻分词: 按空白与中英文标点切. 不依赖 jieba (避免 Phase 2 引入新依赖,
    若后续需要更准的中文分词可在 iter#77+ 升级)."""
    if not text:
        return []
    return [w for w in _WORD_SPLIT_RE.split(text) if w]


def _word_ngrams(text: str, n: int) -> list[str]:
    if n < 1:
        return []
    words = _words(text)
    if len(words) < n:
        return []
    return ["\x00".join(words[i : i + n]) for i in range(len(words) - n + 1)]


def char_ngram_distinct(text: str, n: int) -> float:
    """distinct-n on char n-grams. Returns 0.0 for empty / too-short text.

    Range [0, 1]. 1.0 means every n-gram is unique (max diversity);
    0.5 means half are repeats.
    """
    grams = _char_ngrams(text, n)
    if not grams:
        return 0.0
    return len(set(grams)) / len(grams)


def word_ngram_distinct(text: str, n: int) -> float:
    """distinct-n on word n-grams. Same semantics as char version."""
    grams = _word_ngrams(text, n)
    if not grams:
        return 0.0
    return len(set(grams)) / len(grams)


def char_ngram_overlap(text_a: str, text_b: str, n: int) -> float:
    """Jaccard overlap on char n-gram **sets** between two texts.

    Returns 0.0 if either side has no n-grams. Range [0, 1]: 0 = disjoint,
    1 = identical n-gram sets (the texts could still differ in n-gram counts
    but not in distinct n-grams).
    """
    set_a = set(_char_ngrams(text_a, n))
    set_b = set(_char_ngrams(text_b, n))
    if not set_a or not set_b:
        return 0.0
    inter = set_a & set_b
    union = set_a | set_b
    return len(inter) / len(union)


def word_ngram_overlap(text_a: str, text_b: str, n: int) -> float:
    """Jaccard overlap on word n-gram sets."""
    set_a = set(_word_ngrams(text_a, n))
    set_b = set(_word_ngrams(text_b, n))
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


@dataclass
class RepetitionReport:
    """Bundled repetition view for one narrative sequence.

    ``distinct_char_n`` / ``distinct_word_n`` are per-text averages over the
    whole sequence (mean across tick narrations). ``overlap_*`` are average
    Jaccard between consecutive tick narrations (windowed pair).

    Empty sequences yield all-zero report; callers must check
    ``narration_count`` before drawing inferences.
    """

    narration_count: int = 0
    distinct_char_2: float = 0.0
    distinct_char_3: float = 0.0
    distinct_char_4: float = 0.0
    distinct_word_2: float = 0.0
    distinct_word_3: float = 0.0
    distinct_word_4: float = 0.0
    overlap_char_2_consecutive: float = 0.0
    overlap_char_3_consecutive: float = 0.0
    overlap_char_4_consecutive: float = 0.0
    overlap_word_2_consecutive: float = 0.0
    overlap_word_3_consecutive: float = 0.0
    overlap_word_4_consecutive: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "narration_count": self.narration_count,
            "distinct": {
                "char_2": round(self.distinct_char_2, 4),
                "char_3": round(self.distinct_char_3, 4),
                "char_4": round(self.distinct_char_4, 4),
                "word_2": round(self.distinct_word_2, 4),
                "word_3": round(self.distinct_word_3, 4),
                "word_4": round(self.distinct_word_4, 4),
            },
            "overlap_consecutive": {
                "char_2": round(self.overlap_char_2_consecutive, 4),
                "char_3": round(self.overlap_char_3_consecutive, 4),
                "char_4": round(self.overlap_char_4_consecutive, 4),
                "word_2": round(self.overlap_word_2_consecutive, 4),
                "word_3": round(self.overlap_word_3_consecutive, 4),
                "word_4": round(self.overlap_word_4_consecutive, 4),
            },
            "notes": list(self.notes),
        }


def repetition_report(narrations: list[str]) -> RepetitionReport:
    """Compute repetition view over a sequence of narrations (one per tick).

    Skips empty narrations for per-narration metrics, but includes a note
    when ≥1 skip happened so consumers see signal-not-noise. Overlap is
    over the **non-empty subsequence** so a skipped tick doesn't artificially
    inflate "newness".
    """
    non_empty = [n for n in narrations if n and n.strip()]
    skipped = len(narrations) - len(non_empty)
    rep = RepetitionReport(narration_count=len(non_empty))
    if skipped:
        rep.notes.append(f"skipped_empty_narrations={skipped}")
    if not non_empty:
        return rep

    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    rep.distinct_char_2 = _mean([char_ngram_distinct(t, 2) for t in non_empty])
    rep.distinct_char_3 = _mean([char_ngram_distinct(t, 3) for t in non_empty])
    rep.distinct_char_4 = _mean([char_ngram_distinct(t, 4) for t in non_empty])
    rep.distinct_word_2 = _mean([word_ngram_distinct(t, 2) for t in non_empty])
    rep.distinct_word_3 = _mean([word_ngram_distinct(t, 3) for t in non_empty])
    rep.distinct_word_4 = _mean([word_ngram_distinct(t, 4) for t in non_empty])

    if len(non_empty) >= 2:
        pairs = list(zip(non_empty[:-1], non_empty[1:]))
        rep.overlap_char_2_consecutive = _mean(
            [char_ngram_overlap(a, b, 2) for a, b in pairs]
        )
        rep.overlap_char_3_consecutive = _mean(
            [char_ngram_overlap(a, b, 3) for a, b in pairs]
        )
        rep.overlap_char_4_consecutive = _mean(
            [char_ngram_overlap(a, b, 4) for a, b in pairs]
        )
        rep.overlap_word_2_consecutive = _mean(
            [word_ngram_overlap(a, b, 2) for a, b in pairs]
        )
        rep.overlap_word_3_consecutive = _mean(
            [word_ngram_overlap(a, b, 3) for a, b in pairs]
        )
        rep.overlap_word_4_consecutive = _mean(
            [word_ngram_overlap(a, b, 4) for a, b in pairs]
        )
    else:
        rep.notes.append("only_one_narration_no_overlap")

    return rep


__all__ = [
    "RepetitionReport",
    "char_ngram_distinct",
    "char_ngram_overlap",
    "repetition_report",
    "word_ngram_distinct",
    "word_ngram_overlap",
]
