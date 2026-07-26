"""Deterministic post-resolution expansion gate."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from story.narrative_contract import (
    NarrativeContract,
    NarrativeModel,
    NarrativeValidationReport,
    NarrativeViolation,
    narrative_char_count,
)


EndingValidationPhase = Literal["initial", "repaired", "final"]


class EndingExpansionIssue(NarrativeModel):
    kind: Literal["new_event", "new_character", "new_conflict"]
    evidence: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class EndingCompletionReport(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    phase: EndingValidationPhase
    end_state_reached: bool = False
    resolution_offset: int = Field(default=0, ge=0)
    post_resolution_chars: int = Field(default=0, ge=0)
    needs_compact: bool = False
    accepted: bool = True
    violation_code: str = ""
    issues: list[EndingExpansionIssue] = Field(default_factory=list)


_NEW_CHARACTER = re.compile(
    r"(?:名叫|叫作|自称)[\u3400-\u9fff]{2,5}|"
    r"(?:一个|一名|那名)(?:陌生|新来|不认识|从未见过)?"
    r"[\u3400-\u9fff]{0,8}(?:人|水手|工人|医生|警官|调查员|敌人)"
)
_NEW_CONFLICT = re.compile(
    r"新(?:的)?(?:敌人|冲突|危机|袭击)|"
    r"(?:枪声|爆炸|追杀|伏击|战斗|敌人|袭击|争吵|搏斗)(?:忽然|突然|再次|又)?"
)
_NEW_EVENT = re.compile(
    r"(?:忽然|突然|就在这时|不料|紧接着|谁知).{0,36}"
    r"(?:闯入|袭来|爆炸|响起|出现|冲出|推开|撞开|拔出|追来|倒下|起火)"
)
_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")


def _sentence_for_match(
    text: str,
    *,
    base_offset: int,
    match_start: int,
    match_end: int,
) -> tuple[str, int, int]:
    for sentence in _SENTENCE.finditer(text):
        if sentence.start() <= match_start and sentence.end() >= match_end:
            value = sentence.group(0)
            return value, base_offset + sentence.start(), base_offset + sentence.end()
    return (
        text[match_start:match_end],
        base_offset + match_start,
        base_offset + match_end,
    )


class EndingCompletionValidator:
    """Find new story material after every required end state is reached."""

    def validate(
        self,
        *,
        narrative_text: str,
        contract: NarrativeContract,
        narrative_report: NarrativeValidationReport,
        phase: EndingValidationPhase,
    ) -> EndingCompletionReport:
        required_ids = {item.id for item in contract.required_end_state}
        reached = {
            item.id
            for item in narrative_report.end_state_results
            if item.reached
        }
        end_state_reached = bool(required_ids) and required_ids <= reached
        if not end_state_reached:
            return EndingCompletionReport(
                phase=phase,
                end_state_reached=False,
            )

        evidence_ends: list[int] = []
        for result in narrative_report.end_state_results:
            if not result.reached or not result.evidence:
                continue
            position = narrative_text.rfind(result.evidence)
            if position >= 0:
                evidence_ends.append(position + len(result.evidence))
        # The stopping moment is when both authorities are satisfied. A required
        # event may legitimately finish after an early end-state phrase.
        for result in narrative_report.event_results:
            if result.status != "completed" or not result.evidence:
                continue
            position = narrative_text.rfind(result.evidence)
            if position >= 0:
                evidence_ends.append(position + len(result.evidence))
        if not evidence_ends:
            return EndingCompletionReport(
                phase=phase,
                end_state_reached=True,
            )

        resolution_offset = max(evidence_ends)
        tail = narrative_text[resolution_offset:]
        issues: list[EndingExpansionIssue] = []
        seen: set[tuple[str, int, int]] = set()
        for kind, pattern in (
            ("new_character", _NEW_CHARACTER),
            ("new_conflict", _NEW_CONFLICT),
            ("new_event", _NEW_EVENT),
        ):
            for match in pattern.finditer(tail):
                evidence, start, end = _sentence_for_match(
                    tail,
                    base_offset=resolution_offset,
                    match_start=match.start(),
                    match_end=match.end(),
                )
                key = (kind, start, end)
                if key in seen:
                    continue
                seen.add(key)
                issues.append(
                    EndingExpansionIssue(
                        kind=kind,
                        evidence=evidence,
                        start=start,
                        end=end,
                    )
                )

        needs_compact = bool(issues)
        return EndingCompletionReport(
            phase=phase,
            end_state_reached=True,
            resolution_offset=resolution_offset,
            post_resolution_chars=narrative_char_count(tail),
            needs_compact=needs_compact,
            accepted=not needs_compact,
            violation_code="POST_RESOLUTION_EXPANSION" if needs_compact else "",
            issues=issues,
        )

    @staticmethod
    def violation(
        report: EndingCompletionReport,
    ) -> NarrativeViolation | None:
        if report.accepted:
            return None
        evidence = "；".join(item.evidence for item in report.issues)[:240]
        return NarrativeViolation(
            code="POST_RESOLUTION_EXPANSION",
            message="最终状态达到后又出现新事件、人物或冲突",
            severity="high",
            path="/ending",
            evidence=evidence,
            repair_hint="使用 COMPACT 删除终态后的新增内容，保留事件与终态证据",
        )


__all__ = [
    "EndingCompletionReport",
    "EndingCompletionValidator",
    "EndingExpansionIssue",
    "EndingValidationPhase",
]
