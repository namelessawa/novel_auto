"""Deterministic seam diagnostics for multi-tick section drafts.

The Narrator writes one chunk per tick.  A chunk can be locally good while the
assembled section still repeats an already completed action or restarts from an
earlier state.  These checks deliberately target high-precision surface signs;
semantic replay is handled by SectionEditor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from quality_metrics.repetition import char_ngram_overlap


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])|\n+")


def _normalise_sentence(text: str) -> str:
    return re.sub(r"[\s\"'“”‘’。！？!?，,；;：:—…]+", "", text)


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for raw in _SENTENCE_SPLIT_RE.split(text or ""):
        normalised = _normalise_sentence(raw)
        if len(normalised) >= 6:
            out.append(normalised)
    return out


@dataclass(frozen=True)
class SectionSeamFinding:
    seam_after_part: int
    code: str
    evidence: str
    severity: str = "medium"

    def to_dict(self) -> dict:
        return {
            "seam_after_part": self.seam_after_part,
            "code": self.code,
            "evidence": self.evidence,
            "severity": self.severity,
        }


@dataclass
class SectionSeamReport:
    part_count: int
    findings: list[SectionSeamFinding] = field(default_factory=list)
    max_leading_char4_overlap: float = 0.0

    @property
    def requires_edit(self) -> bool:
        return any(f.severity == "high" for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "part_count": self.part_count,
            "requires_edit": self.requires_edit,
            "max_leading_char4_overlap": round(self.max_leading_char4_overlap, 4),
            "findings": [f.to_dict() for f in self.findings],
        }


def section_seam_report(parts: list[str]) -> SectionSeamReport:
    """Inspect adjacent tick chunks for exact replay and recycled openings."""
    non_empty = [p.strip() for p in parts if p and p.strip()]
    report = SectionSeamReport(part_count=len(non_empty))
    for idx, part in enumerate(non_empty, 1):
        sentences = _sentences(part)
        seen: set[str] = set()
        duplicated: list[str] = []
        for sentence in sentences:
            if sentence in seen and sentence not in duplicated:
                duplicated.append(sentence)
            seen.add(sentence)
        if duplicated:
            report.findings.append(
                SectionSeamFinding(
                    seam_after_part=idx,
                    code="S0_INTERNAL_SENTENCE_REPLAY",
                    evidence=" / ".join(duplicated[:3]),
                    severity="high",
                )
            )
    for idx, (previous, current) in enumerate(zip(non_empty[:-1], non_empty[1:]), 1):
        previous_sentences = set(_sentences(previous))
        current_sentences = _sentences(current)
        duplicates = [s for s in current_sentences if s in previous_sentences]
        if duplicates:
            report.findings.append(
                SectionSeamFinding(
                    seam_after_part=idx,
                    code="S1_EXACT_SENTENCE_REPLAY",
                    evidence=" / ".join(duplicates[:3]),
                    severity="high",
                )
            )

        previous_tail = previous[-500:]
        current_head = current[:300]
        overlap = char_ngram_overlap(previous_tail, current_head, 4)
        report.max_leading_char4_overlap = max(
            report.max_leading_char4_overlap, overlap
        )
        # 4-gram Jaccard above 0.22 at a seam is unusually high for separate
        # Chinese prose chunks and normally means the new chunk replays the
        # prior state.  Keep it medium: recurring names/objects can be valid.
        if overlap >= 0.22:
            report.findings.append(
                SectionSeamFinding(
                    seam_after_part=idx,
                    code="S2_LEADING_STATE_OVERLAP",
                    evidence=f"char4_jaccard={overlap:.3f}",
                    severity="medium",
                )
            )

        previous_last = _sentences(previous)[-1:] or []
        current_first = current_sentences[:1]
        if previous_last and current_first and previous_last[0] == current_first[0]:
            report.findings.append(
                SectionSeamFinding(
                    seam_after_part=idx,
                    code="S3_DUPLICATED_BOUNDARY_SENTENCE",
                    evidence=current_first[0],
                    severity="high",
                )
            )
    return report


__all__ = [
    "SectionSeamFinding",
    "SectionSeamReport",
    "section_seam_report",
]
