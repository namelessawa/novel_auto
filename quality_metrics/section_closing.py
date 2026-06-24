"""Phase 6-C iter#C1 — C6 章末无悬念 det check (lite).

> Aligns with `docs/design/novel_quality_critique_and_iteration.md`:
>
> | code | trigger |
> | --- | --- |
> | C6   | 章节结尾无悬念、无未解问题、无新欲望 (medium) |

## Why det-only is hard here

C6 is a NEGATIVE condition ("absence of suspense"), which is structurally
FP-prone for a det layer — many perfectly good narratives end on a clean
action / object detail without any explicit "open question" marker, and
flagging those would be noise. The iter#7 stats endpoint verdict explicitly
noted this risk: "C6 章末无悬念 det check — semantic, det 层易 FP".

## What we do instead

Conservative heuristic — only trigger on **explicit closure language at the
tail**. Patterns like:

* 尘埃落定
* 终于(结束|完结|落幕|平息)
* 至此(告一段落|画上句号)
* 再无(悬念|波澜|疑问|未解)
* (此事|这件事|事情|案子|风波)(到此|至此)(结束|完结|为止|告一段落)
* 便(是|算是)(结束|结局|尾声|画上句号)
* 故事(到此|至此)?(就)?(结束|完结)
* 一切(都)?(尘埃落定|归于平静)

Marker must appear in the **last 60 chars** (tail), and the text overall
must be ≥ 40 chars (very short fragments skip).

## What we do NOT do

* Do not flag based on "no question mark in last sentence" — too noisy.
* Do not flag based on absence of open_loop hints — narrative scope, not
  paragraph scope.
* Do not run on very short text (< 40 chars) — short narratives don't have
  a "section closing" responsibility.

env kill switch: ``SECTION_CLOSING_ENABLE=0`` disables the wrapper in
``agents/quality_checks.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Tail closure patterns — each (name, regex) tuple. Names are short for
# evidence readability. Regexes intentionally narrow — no greedy CJK ranges,
# no optional tail filler that would let middle-of-paragraph mentions slip
# through (the tail-window scope handles "must be at end").
# Bridge — short CJK / comma / 的 between marker tokens, kept ≤ 12 chars
# so we don't over-greedily span sentences.
_BRIDGE = r"[一-龥,，、的 ]{0,12}?"

_CLOSURE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("尘埃落定", re.compile(r"尘埃落定")),
    ("终于结束", re.compile(r"终于(?:结束|完结|落幕|平息)")),
    # 至此(, 这件事)?(画上句号|告一段落) — bridge允许 0-12 字 CJK/逗号/的
    ("至此告一段落", re.compile(r"至此" + _BRIDGE + r"(?:告一段落|画上句号)")),
    ("再无悬念", re.compile(r"再无(?:悬念|波澜|疑问|未解)")),
    # 便是(这场十年风波的)?结局 — bridge 允许中间名词短语
    ("便是结局", re.compile(r"便(?:是|算是)" + _BRIDGE + r"(?:结束|结局|尾声|画上句号)")),
    (
        "事情到此结束",
        re.compile(
            r"(?:此事|这件事|事情|案子|风波)"
            r"(?:到此|至此)?"
            r"(?:结束|完结|为止|告一段落|落幕)"
        ),
    ),
    ("故事到此结束", re.compile(r"故事(?:到此|至此)?(?:就)?(?:结束|完结)")),
    ("一切归于平静", re.compile(r"一切(?:都)?(?:尘埃落定|归于平静)")),
    ("总算尘埃落定", re.compile(r"总算(?:尘埃落定|结束|完结|平息)")),
)

# Minimum text length to bother checking — short narratives don't have a
# "section closing" semantic load. Picked 25 char so that 1-event closure
# narratives ("十年悬案, 案犯今早伏法。尘埃落定。" ~ 36 chars) still test,
# but micro-action narratives ("雨停了。" / "他抬头。") still skip.
_MIN_TEXT_LEN = 25

# Tail window — closure language must appear within the last N chars.
# Picked 60 char (~2-3 sentences) so a closure phrase in the middle of a
# longer narrative does not trip — only an actual end-of-narrative closure.
_TAIL_WINDOW = 60


@dataclass(frozen=True)
class SectionClosingReport:
    """C6 detection result for a single narrative chunk."""

    text_length: int
    matched_markers: list[str]
    c6_triggered: bool
    c6_evidence: str

    def to_dict(self) -> dict:
        return {
            "text_length": self.text_length,
            "matched_markers": list(self.matched_markers),
            "c6": {"triggered": self.c6_triggered, "evidence": self.c6_evidence},
        }


def c6_section_closing_check(text: str) -> tuple[bool, str]:
    """C6: explicit closure language at narrative tail.

    Returns ``(triggered, evidence)``. ``evidence`` is empty string when
    not triggered.

    Conservative trigger — only when an explicit closure marker
    ("尘埃落定" / "至此告一段落" / etc.) appears in the **last 60 chars**
    of a ≥40-char narrative. See module docstring for rationale.
    """
    if not text:
        return False, ""
    stripped = text.strip()
    if len(stripped) < _MIN_TEXT_LEN:
        return False, ""
    tail = stripped[-_TAIL_WINDOW:]
    matched: list[str] = []
    for name, pat in _CLOSURE_PATTERNS:
        if pat.search(tail):
            matched.append(name)
    if not matched:
        return False, ""
    evidence = (
        f"段末 {min(_TAIL_WINDOW, len(stripped))} 字内出现 closure 语言: "
        + ", ".join(matched)
        + f". tail={tail.strip()!r}"
    )
    return True, evidence


def section_closing_report(text: str) -> SectionClosingReport:
    """Run C6 on a narrative chunk, return structured report."""
    triggered, evidence = c6_section_closing_check(text)
    matched: list[str] = []
    if triggered and text:
        tail = text.strip()[-_TAIL_WINDOW:]
        for name, pat in _CLOSURE_PATTERNS:
            if pat.search(tail):
                matched.append(name)
    return SectionClosingReport(
        text_length=len(text or ""),
        matched_markers=matched,
        c6_triggered=triggered,
        c6_evidence=evidence,
    )


__all__ = [
    "SectionClosingReport",
    "c6_section_closing_check",
    "section_closing_report",
]
