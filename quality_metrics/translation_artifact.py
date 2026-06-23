"""Phase 6-C fourth slice — translation artifact det check (E7 lite).

> Aligns with `docs/design/novel_quality_critique_and_iteration.md`:
>
> | code | trigger |
> | --- | --- |
> | E7   | 翻译腔: 密集出现 "这是一个……的人"、"对于……来说" |
>
> Why E7 next:
> - Pattern-matchable — the failure mode is a small set of recognisable
>   translation-clone constructs (English-derived passive 被 X 所 Y,
>   "对于 X 来说", "这是一个 ... 的 ...", long de-chains).
> - Healthy Chinese long-form prose almost never uses these; the LLM
>   only slips into them under specific failure modes (high temp,
>   thin training-data signal). Det layer catches the slip without
>   needing the LLM critic to look.

Heuristic: trigger when the sum of distinct pattern hits ≥ 2 across the
chunk. A single accidental hit (one "对于 X 来说" in a 1000-char paragraph)
is not enough; two-or-more is the inflection where it reads as translation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Each pattern is a (name, compiled regex) tuple — keep names short so
# evidence lines stay readable in critic logs.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # "对于 X 来说" / "对 X 而言" — translation of "for X" / "to X"
    ("对于…来说", re.compile(r"对于[一-龥A-Za-z0-9 ,，、]{1,12}来说")),
    ("对…而言", re.compile(r"对[一-龥A-Za-z0-9 ,，、]{1,10}而言")),
    # "这是一个 N 字内 的 [名词]" — translation of "this is a/an ... X"
    ("这是一个…的", re.compile(r"这是一个[一-龥]{1,18}的[一-龥]{1,4}")),
    # 被 X 所 Y — Chinese rarely uses this for non-formal prose; LLMs over-use it
    ("被…所…", re.compile(r"被[一-龥]{1,8}所[一-龥]{1,4}")),
    # Long de-chain: 3+ "X 的 Y 的 Z 的" within 24 chars
    ("长定语链", re.compile(r"(?:[一-龥]{1,4}的){3,}[一-龥]{1,4}")),
    # "不仅…而且…" — formulaic translation cadence (overused in AI prose)
    ("不仅…而且…", re.compile(r"不仅[一-龥,，、 ]{2,30}而且")),
    # "由于…的原因" — translation-style cause marker
    ("由于…的原因", re.compile(r"由于[一-龥]{2,15}的原因")),
)


@dataclass(frozen=True)
class TranslationArtifactReport:
    """E7 detection result for a single narrative chunk."""

    text_length: int
    pattern_hits: dict[str, int]
    total_hits: int
    e7_triggered: bool
    e7_evidence: str

    def to_dict(self) -> dict:
        return {
            "text_length": self.text_length,
            "pattern_hits": dict(self.pattern_hits),
            "total_hits": self.total_hits,
            "e7": {"triggered": self.e7_triggered, "evidence": self.e7_evidence},
        }


def e7_translation_artifact_check(
    text: str, min_hits: int = 2
) -> tuple[bool, str, dict[str, int]]:
    """E7: 翻译腔 pattern density ≥ ``min_hits``.

    Returns ``(triggered, evidence, per_pattern_counts)``. The default
    threshold of 2 is the minimum that distinguishes "isolated accident"
    from "the writer keeps falling into the same construction".
    """
    if not text:
        return False, "", {}
    hits: dict[str, int] = {}
    for name, pat in _PATTERNS:
        n = len(pat.findall(text))
        if n > 0:
            hits[name] = n
    total = sum(hits.values())
    if total < min_hits:
        return False, "", hits
    # Pick the top-3 offending patterns by count for the evidence line —
    # gives the critic something concrete to point at without dumping the
    # whole hit table.
    top = sorted(hits.items(), key=lambda kv: -kv[1])[:3]
    summary = ", ".join(f"{name}×{n}" for name, n in top)
    evidence = f"total_hits={total} ≥ {min_hits}. Top: {summary}"
    return True, evidence, hits


def translation_artifact_report(
    text: str, *, min_hits: int = 2
) -> TranslationArtifactReport:
    """Run E7 on a narrative chunk, return combined report."""
    triggered, evidence, hits = e7_translation_artifact_check(text, min_hits=min_hits)
    return TranslationArtifactReport(
        text_length=len(text or ""),
        pattern_hits=hits,
        total_hits=sum(hits.values()),
        e7_triggered=triggered,
        e7_evidence=evidence,
    )


__all__ = [
    "TranslationArtifactReport",
    "e7_translation_artifact_check",
    "translation_artifact_report",
]
