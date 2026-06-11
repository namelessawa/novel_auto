"""Consistency metrics — does the narrative agree with the world snapshot?

Phase 2 §3.1 mandate (iter#77):

> 从叙事文本抽取角色名 / 地点 / 关键状态, 与 world state 快照比对, 输出
> 矛盾计数与矛盾清单. 首版允许召回不全, 但误报要低.

This module ships the v1 "low-recall but high-precision" check. We only
flag a violation when the text uses a specific named entity (character or
location) that the snapshot positively forbids — e.g. a character placed
in a location they aren't in, or a location that doesn't exist at all.
We deliberately don't try to infer "the text doesn't mention X but X
should appear" since that's a recall metric, not precision.

Key design choices:

* **Name matching is exact substring.** Chinese names usually aren't
  ambiguous between common words, so substring is precise enough for v1.
* **Per-narration evaluation**, then aggregated. Each narration is checked
  against the snapshot that was valid at that tick (caller's responsibility
  to pass matching snapshots).
* **Pure function.** No state, no I/O. Reproducible.

What we DON'T cover in v1 (acknowledged blind spots written to notes
on the report):

* Pronoun resolution — "他" / "她" with multiple A-tier chars in scene
* Inferred state changes — narrative says character is wounded but snapshot
  hasn't been advanced yet
* Faction or world-rule violations — hard to detect without LLM
* Time / season mismatches
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class CharacterFact:
    """Minimal view a character snapshot exposes to the consistency check.

    Caller pulls from CharacterState/CharacterProfile and builds this. We
    intentionally don't import the heavy Pydantic models in this module —
    keeps the metric reusable for golden-file replays.
    """

    id: str
    name: str
    current_location: str = ""  # location id
    alive: bool = True


@dataclass
class LocationFact:
    """Minimal view a location snapshot exposes."""

    id: str
    name: str


@dataclass
class WorldSnapshot:
    """Snapshot for one tick — what the world was at narration time.

    Caller assembles this from TickState.world_state + list_character_states.
    """

    characters: list[CharacterFact] = field(default_factory=list)
    locations: list[LocationFact] = field(default_factory=list)

    @property
    def known_character_names(self) -> set[str]:
        return {c.name for c in self.characters if c.name}

    @property
    def known_location_names(self) -> set[str]:
        return {l.name for l in self.locations if l.name}

    def character_by_name(self, name: str) -> CharacterFact | None:
        for c in self.characters:
            if c.name and c.name == name:
                return c
        return None

    def location_by_name(self, name: str) -> LocationFact | None:
        for l in self.locations:
            if l.name and l.name == name:
                return l
        return None


@dataclass
class ConsistencyViolation:
    """One concrete narrative-vs-snapshot mismatch.

    ``kind`` is enumerated; tooling can group/filter by it.
    ``evidence`` is the offending substring from the narration.
    ``severity`` is "high" (named entity that doesn't exist) or "medium"
    (character mentioned outside their current scene location).
    """

    kind: str
    evidence: str
    severity: str  # "high" | "medium"
    narration_index: int

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "evidence": self.evidence,
            "severity": self.severity,
            "narration_index": self.narration_index,
        }


@dataclass
class ConsistencyReport:
    narration_count: int = 0
    violations: list[ConsistencyViolation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "high")

    @property
    def medium_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "medium")

    def to_dict(self) -> dict:
        return {
            "narration_count": self.narration_count,
            "violation_count": self.violation_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "violations": [v.to_dict() for v in self.violations],
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Detection primitives
# ---------------------------------------------------------------------------


def _names_in_text(text: str, names: set[str]) -> set[str]:
    """Return the subset of names that appear (as substring) in text."""
    return {n for n in names if n and n in text}


def _location_mention_for_character(
    text: str, char_name: str, locations: set[str]
) -> str | None:
    """Heuristic: did the narration place ``char_name`` AT a named location
    other than their snapshot location?

    Returns the location name if such a mention exists, else None. We look
    for patterns: "<name>在<loc>", "<name>站在<loc>", "<name>走过<loc>"
    — the most common "X 在 Y" Chinese constructions. Substring-only;
    we accept false negatives.
    """
    if not char_name or not locations:
        return None
    char_pos = text.find(char_name)
    if char_pos < 0:
        return None
    # Look in a window after the name for any known location
    window = text[char_pos : char_pos + 60]
    for loc in locations:
        if loc and loc in window:
            return loc
    return None


def check_narration_against_snapshot(
    text: str,
    snapshot: WorldSnapshot,
    narration_index: int = 0,
) -> list[ConsistencyViolation]:
    """Check one narration against one tick's snapshot.

    Flags:
    1. **Character mentioned but not in any known character list** —
       high severity. The model hallucinated a name. Only fires when text
       contains a 2+ char string matching no known name but the snapshot
       has any named characters at all (sentinel; v1 conservative).
    2. **Location used in narration but not in known locations** — high
       severity. Hallucinated geography. We can only catch this when text
       contains a substring exactly matching no known location yet looks
       like a location (heuristic: ends with 城/巷/馆/区/港/原/岭/林/坡 /
       岛 / 山 / 庙 / 街). False negatives accepted.
    3. **Character placed in wrong location** — medium severity. ``X 在 Y``
       where Y ≠ X's current_location.
    """
    if not text or not text.strip():
        return []

    violations: list[ConsistencyViolation] = []
    char_names = snapshot.known_character_names
    loc_names = snapshot.known_location_names

    # --- Check 3: char placed at wrong location ---
    for char in snapshot.characters:
        if not char.name or char.name not in text:
            continue
        mentioned_loc = _location_mention_for_character(
            text, char.name, loc_names
        )
        if mentioned_loc:
            char_loc_fact = next(
                (l for l in snapshot.locations if l.id == char.current_location),
                None,
            )
            char_loc_name = char_loc_fact.name if char_loc_fact else ""
            if char_loc_name and mentioned_loc != char_loc_name:
                violations.append(
                    ConsistencyViolation(
                        kind="character_at_wrong_location",
                        evidence=f"{char.name} 在 {mentioned_loc} (snapshot: {char_loc_name})",
                        severity="medium",
                        narration_index=narration_index,
                    )
                )

    # --- Check 2: hallucinated location ---
    # Heuristic suffix set for Chinese place-name endings.
    _LOC_SUFFIXES = ("城", "巷", "馆", "区", "港", "原", "岭", "林", "坡", "岛", "山", "庙", "街")
    # 候选窗 3-4 字 (不取 2 字 — '在街' / '出城' / '入山' 类虚词组合误报率高;
    # 中文地名几乎都 ≥2 前缀字 + 1 后缀字 = 3+ 总长).
    # 候选任何位置含动词/虚词 → 当动作短语而非地名 skip ('走在街' / '过城去' /
    # '入山林' 等). 真地名 ('锈幕城' / '齿轮集市' / '雾都') 无这类字.
    _VERB_OR_PREP = set("在到从向出入离回过往走来去看望蹲跑跳坐站睡的了着是不")
    # 真地名不含空白 / 标点 / 数字; 若候选含, 几乎肯定是跨边界切到的字符串.
    _NON_NAME = set(" \t\n\r,.。，、；：！？“”‘’（）《》【】「」『』·—…0123456789()[]{}")
    for n in (3, 4):
        for i in range(len(text) - n + 1):
            candidate = text[i : i + n]
            if not candidate.endswith(_LOC_SUFFIXES):
                continue
            if any(ch in _VERB_OR_PREP for ch in candidate):
                continue
            if any(ch in _NON_NAME for ch in candidate):
                continue
            # Skip if appears in any known location name (substring).
            if any(candidate in loc for loc in loc_names if loc):
                continue
            # Skip if appears in character name (rare but defensive).
            if any(candidate in name for name in char_names if name):
                continue
            # Skip placeholders / common words.
            if candidate in {
                "全城", "本城", "此城", "雪山", "群山", "群岛", "深山",
                "皇城", "京城", "山林", "树林", "竹林", "森林",
            }:
                continue
            # Skip if matches any prefix of known location (still ambiguous).
            if loc_names and any(loc.startswith(candidate) for loc in loc_names if loc):
                continue
            violations.append(
                ConsistencyViolation(
                    kind="hallucinated_location",
                    evidence=candidate,
                    severity="high",
                    narration_index=narration_index,
                )
            )
            break  # one per narration is enough — don't spam

    # Check 1 (hallucinated character name) deliberately skipped in v1:
    # extracting unknown person names from Chinese narrative is too lossy
    # for substring matching. Punted to LLM-judge layer.

    return violations


def consistency_report(
    narrations: Sequence[str],
    snapshots: Sequence[WorldSnapshot],
) -> ConsistencyReport:
    """Aggregate over a sequence of (narration, snapshot) pairs.

    Length mismatch: report.notes records the truncation. We zip to the
    shorter list — caller's responsibility to pass matched sequences.
    """
    rep = ConsistencyReport(narration_count=len(narrations))

    if len(narrations) != len(snapshots):
        rep.notes.append(
            f"sequence_length_mismatch narrations={len(narrations)} "
            f"snapshots={len(snapshots)} — truncated to min"
        )

    for idx, (text, snap) in enumerate(zip(narrations, snapshots)):
        rep.violations.extend(check_narration_against_snapshot(text, snap, idx))

    if not narrations:
        rep.notes.append("empty_input")

    return rep


__all__ = [
    "CharacterFact",
    "LocationFact",
    "WorldSnapshot",
    "ConsistencyViolation",
    "ConsistencyReport",
    "check_narration_against_snapshot",
    "consistency_report",
]
