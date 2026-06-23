"""Phase 6-C third slice — character signal det checks (B4 lite).

> Aligns with `docs/design/novel_quality_critique_and_iteration.md`:
>
> | code | trigger |
> | --- | --- |
> | B4   | 内心独白字数 > (行动 + 对话) 字数 × 1.5 |
>
> Why B4 next:
> - Spec value is countable when we accept a lite definition: count chars
>   inside explicit inner-monologue markers vs chars inside dialogue quotes.
>   Pure "action chars" requires Chinese POS tagging — out of scope for the
>   det layer; LLM critic catches the remainder.
> - Phase 6-A.2 271 narratives showed healthy long-range prose carries
>   almost no inner monologue (verified by sample inspection), so the
>   threshold rarely fires on healthy bench and catches the degenerate
>   "he thought / she realized / he knew" stack-up that's a common LLM
>   long-run failure mode.

Heuristic: B4 triggers when inner-monologue char count exceeds dialogue
char count × 1.5 AND the absolute inner-monologue ratio over the whole
text crosses an additional floor (avoids tiny-text noise).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Explicit inner-monologue markers — when one of these appears, the
# surrounding sentence (between adjacent CJK punctuation) is treated as
# inner monologue. The list is intentionally tight: each marker is
# unambiguously about a character's *unvoiced* thinking. Body-language
# verbs ("看着 / 转身 / 抬头") deliberately stay out.
_INNER_MARKERS: tuple[str, ...] = (
    "心想",
    "心里想",
    "心中想",
    "心中暗",
    "暗想",
    "暗忖",
    "默想",
    "默念",
    "想道",
    "想到",
    "想着",
    "脑海中",
    "脑海里",
    "脑子里",
    "脑中浮",
    "意识到",
    "回想起",
    "回忆起",
    "回想着",
)

# Sentence boundary in Chinese prose (same as prose_dynamics).
_SENT_END_RE = re.compile(r"[。!?！？；;…]+")

# Dialogue quote pairs — straight (") and Chinese full-width (「 」 / “ ”).
_QUOTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\"([^\"]+?)\""),
    re.compile(r"“([^”]+?)”"),
    re.compile(r"「([^」]+?)」"),
)


def count_dialogue_chars(text: str) -> int:
    """Sum of CJK chars inside any supported quote pair.

    Counts only the *content* between quotes, not the quotes themselves.
    Overlap across multiple quote styles is implausible — straight and
    Chinese quotes do not nest in practice, so summing per-pattern is safe.
    """
    if not text:
        return 0
    total = 0
    for pat in _QUOTE_PATTERNS:
        for m in pat.finditer(text):
            inner = m.group(1)
            total += sum(1 for ch in inner if "一" <= ch <= "鿿")
    return total


def _sentences_with_offsets(text: str) -> list[tuple[int, int, str]]:
    """Split text into (start, end, sentence) triples by Chinese end-marks.

    Returned offsets are character indices into ``text`` and exclude the
    boundary punctuation itself. Empty pieces are filtered out so blank
    sentences (from runs of punctuation) don't inflate counts.
    """
    if not text:
        return []
    out: list[tuple[int, int, str]] = []
    cursor = 0
    for m in _SENT_END_RE.finditer(text):
        piece = text[cursor : m.start()]
        if piece.strip():
            out.append((cursor, m.start(), piece))
        cursor = m.end()
    tail = text[cursor:]
    if tail.strip():
        out.append((cursor, len(text), tail))
    return out


def count_inner_monologue_chars(text: str) -> tuple[int, list[str]]:
    """Sum of CJK chars in sentences that contain an inner-monologue marker.

    A sentence whose chars are also inside a dialogue quote is NOT counted —
    a character saying ``"我想到一件事"`` aloud is dialogue, not monologue.
    Returns ``(chars, evidence_snippets)`` where evidence is a list of up
    to 3 short snippets (≤24 chars each) to help the critic locate the hit.
    """
    if not text:
        return 0, []
    # Build a mask of indices that fall inside any quote — those sentences'
    # marker hits are dialogue, not monologue.
    in_quote = [False] * len(text)
    for pat in _QUOTE_PATTERNS:
        for m in pat.finditer(text):
            for i in range(m.start(1), m.end(1)):
                if i < len(in_quote):
                    in_quote[i] = True
    total = 0
    evidence: list[str] = []
    for start, end, sent in _sentences_with_offsets(text):
        # Marker-aware quote skip — find the marker's absolute position in
        # `text` and skip if that position falls inside any quote. Sentence
        # spans can straddle a quote boundary ('他说:"我想到 X"。' splits
        # before the trailing "。", so the span's start sits outside the
        # quote even though the marker is inside), so we cannot rely on
        # span corners alone — checking the marker position is precise.
        marker_in_quote = False
        for marker in _INNER_MARKERS:
            pos = sent.find(marker)
            if pos < 0:
                continue
            abs_pos = start + pos
            if abs_pos < len(in_quote) and in_quote[abs_pos]:
                marker_in_quote = True
                break
            # marker exists outside any quote — this sentence is inner monologue
            break
        else:
            # no marker matched at all — not inner monologue
            continue
        if marker_in_quote:
            continue
        cjk = sum(1 for ch in sent if "一" <= ch <= "鿿")
        total += cjk
        if len(evidence) < 3:
            evidence.append(sent.strip()[:24])
    return total, evidence


def count_total_cjk_chars(text: str) -> int:
    """CJK char count — denominator for the floor-ratio guard."""
    if not text:
        return 0
    return sum(1 for ch in text if "一" <= ch <= "鿿")


@dataclass(frozen=True)
class CharacterSignalReport:
    """B4 detection result for a single narrative chunk."""

    text_length: int
    cjk_chars: int
    dialogue_chars: int
    inner_monologue_chars: int
    b4_triggered: bool
    b4_evidence: str
    inner_snippets: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "text_length": self.text_length,
            "cjk_chars": self.cjk_chars,
            "dialogue_chars": self.dialogue_chars,
            "inner_monologue_chars": self.inner_monologue_chars,
            "b4": {"triggered": self.b4_triggered, "evidence": self.b4_evidence},
            "snippets": list(self.inner_snippets),
        }


def b4_inner_monologue_check(
    text: str,
    *,
    ratio_to_dialogue: float = 1.5,
    min_ratio_to_total: float = 0.40,
    min_inner_chars: int = 60,
) -> tuple[bool, str, dict]:
    """B4 lite: inner-monologue chars exceed dialogue chars × ``ratio_to_dialogue``.

    Three guards prevent noise:
    1. ``min_inner_chars`` — absolute floor; below this the ratio is too
       sensitive to short paragraphs.
    2. ``min_ratio_to_total`` — inner chars must be at least this fraction
       of total CJK chars; otherwise a dialogue-free flash-of-thought paragraph
       (legitimate, e.g. 100 chars of pure recollection) gets a pass.
    3. Empty-dialogue case: when dialogue_chars == 0, fall back to comparing
       inner against ``(total_cjk - inner)`` to avoid division-by-zero
       triggering on every dialogue-free paragraph.
    """
    if not text:
        return False, "", {}
    cjk = count_total_cjk_chars(text)
    dialogue = count_dialogue_chars(text)
    inner, snippets = count_inner_monologue_chars(text)
    stats = {
        "cjk_chars": cjk,
        "dialogue_chars": dialogue,
        "inner_monologue_chars": inner,
        "snippets": snippets,
    }
    if inner < min_inner_chars:
        return False, "", stats
    if cjk == 0 or (inner / cjk) < min_ratio_to_total:
        return False, "", stats
    # Compare inner vs dialogue (or vs non-inner remainder if no dialogue).
    if dialogue > 0:
        threshold = dialogue * ratio_to_dialogue
        if inner <= threshold:
            return False, "", stats
        evidence = (
            f"inner={inner} > dialogue×{ratio_to_dialogue:.1f} "
            f"(dialogue={dialogue}, inner/total={inner / cjk:.0%}). "
            f"Sample: {snippets[0] if snippets else '—'}"
        )
        return True, evidence, stats
    # No dialogue at all — compare inner to non-inner remainder ×1.5.
    # remainder==0 is the degenerate "everything is inner monologue" case
    # and must trigger; otherwise dialogue-free pure-monologue paragraphs
    # slip past despite being the exact failure mode B4 targets.
    remainder = cjk - inner
    if remainder > 0 and inner <= remainder * ratio_to_dialogue:
        return False, "", stats
    evidence = (
        f"inner={inner} > non-inner×{ratio_to_dialogue:.1f} "
        f"(non-inner={remainder}, dialogue=0, inner/total={inner / cjk:.0%}). "
        f"Sample: {snippets[0] if snippets else '—'}"
    )
    return True, evidence, stats


def character_signal_report(
    text: str,
    *,
    ratio_to_dialogue: float = 1.5,
    min_ratio_to_total: float = 0.40,
    min_inner_chars: int = 60,
) -> CharacterSignalReport:
    """Run B4 on a narrative chunk, return combined report."""
    triggered, evidence, stats = b4_inner_monologue_check(
        text,
        ratio_to_dialogue=ratio_to_dialogue,
        min_ratio_to_total=min_ratio_to_total,
        min_inner_chars=min_inner_chars,
    )
    return CharacterSignalReport(
        text_length=len(text or ""),
        cjk_chars=stats.get("cjk_chars", 0),
        dialogue_chars=stats.get("dialogue_chars", 0),
        inner_monologue_chars=stats.get("inner_monologue_chars", 0),
        b4_triggered=triggered,
        b4_evidence=evidence,
        inner_snippets=tuple(stats.get("snippets", [])),
    )


__all__ = [
    "CharacterSignalReport",
    "b4_inner_monologue_check",
    "character_signal_report",
    "count_dialogue_chars",
    "count_inner_monologue_chars",
    "count_total_cjk_chars",
]
