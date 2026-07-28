"""Deterministic semantic-recall probes for long-range acceptance."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from story.models import (
    CanonicalState,
    ContextManifest,
    MemoryCanonicalClaim,
    StoryModel,
)


SemanticRecallCategory = Literal[
    "knowledge_boundary",
    "relationship",
    "item",
    "location_rule",
    "promise",
    "main_thread",
    "stale_fact",
]


class SemanticRecallProbe(StoryModel):
    id: str = Field(min_length=1)
    due_section: int = Field(ge=1)
    category: SemanticRecallCategory
    required_memory_ids: list[str] = Field(default_factory=list)
    forbidden_memory_ids: list[str] = Field(default_factory=list)
    required_prose: list[str] = Field(default_factory=list)
    forbidden_prose: list[str] = Field(default_factory=list)
    canonical_claims: list[MemoryCanonicalClaim] = Field(default_factory=list)


class SemanticRecallResult(StoryModel):
    probe_id: str
    category: SemanticRecallCategory
    due_section: int = Field(ge=1)
    accepted: bool = False
    selected_memory_ids: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    violation_codes: list[str] = Field(default_factory=list)


def _canonical_value(state: CanonicalState, path: str) -> tuple[Any, bool]:
    value: Any = state.model_dump(mode="python")
    for raw in path.strip("/").split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or key not in value:
            return None, False
        value = value[key]
    return value, True


def _claim_matches(state: CanonicalState, claim: MemoryCanonicalClaim) -> bool:
    actual, exists = _canonical_value(state, claim.path)
    if not exists:
        return False
    if claim.operator == "equals":
        return actual == claim.expected
    if isinstance(actual, dict):
        return claim.expected in actual or claim.expected in actual.values()
    if isinstance(actual, (list, tuple, set, str)):
        return claim.expected in actual
    return False


class SemanticRecallValidator:
    """Prove selected memories were used correctly in prose and final state."""

    def validate(
        self,
        probe: SemanticRecallProbe,
        *,
        manifest: ContextManifest,
        narrative_text: str,
        final_state: CanonicalState,
    ) -> SemanticRecallResult:
        selected = set(manifest.selected_memory_ids)
        violations: list[str] = []
        evidence: list[str] = []

        missing_memories = sorted(set(probe.required_memory_ids) - selected)
        if missing_memories:
            violations.append("REQUIRED_MEMORY_NOT_SELECTED")
        forbidden_selected = sorted(set(probe.forbidden_memory_ids) & selected)
        if forbidden_selected:
            violations.append("STALE_MEMORY_SELECTED")

        for phrase in probe.required_prose:
            if phrase not in narrative_text:
                violations.append("SELECTED_MEMORY_NOT_USED_IN_PROSE")
            else:
                evidence.append(phrase)
        for phrase in probe.forbidden_prose:
            if phrase in narrative_text:
                violations.append("STALE_OR_FORBIDDEN_FACT_USED")
        for claim in probe.canonical_claims:
            if not _claim_matches(final_state, claim):
                violations.append("SEMANTIC_RECALL_STATE_MISMATCH")

        return SemanticRecallResult(
            probe_id=probe.id,
            category=probe.category,
            due_section=probe.due_section,
            accepted=not violations,
            selected_memory_ids=manifest.selected_memory_ids,
            evidence=evidence,
            violation_codes=list(dict.fromkeys(violations)),
        )


def recorded_semantic_recall_probes() -> list[SemanticRecallProbe]:
    """Seven frozen probes exercised at 10/20/30-section distances."""

    return [
        SemanticRecallProbe(
            id="knowledge_boundary_10",
            due_section=10,
            category="knowledge_boundary",
            required_memory_ids=["memory_knowledge_boundary"],
            required_prose=["沈砚仍不知道旧信末页的落款"],
            forbidden_prose=["沈砚早已知道旧信末页的落款"],
            canonical_claims=[
                MemoryCanonicalClaim(
                    path="/character_knowledge/shen_yan",
                    expected="不知道旧信末页的落款",
                    operator="contains",
                )
            ],
        ),
        SemanticRecallProbe(
            id="relationship_10",
            due_section=10,
            category="relationship",
            required_memory_ids=["memory_relationship"],
            required_prose=["两人仍是共同维护灯塔的多年搭档"],
            canonical_claims=[
                MemoryCanonicalClaim(
                    path="/relationships/shen_yan:lin_qiu/description",
                    expected="共同维护灯塔的多年搭档",
                )
            ],
        ),
        SemanticRecallProbe(
            id="stale_fact_10",
            due_section=10,
            category="stale_fact",
            forbidden_memory_ids=["memory_stale_holder"],
            forbidden_prose=["旧信仍由沈砚保管"],
            canonical_claims=[
                MemoryCanonicalClaim(
                    path="/items/letter/holder",
                    expected="lin_qiu",
                )
            ],
        ),
        SemanticRecallProbe(
            id="item_20",
            due_section=20,
            category="item",
            required_memory_ids=["memory_item_holder"],
            required_prose=["旧信仍由林秋保管"],
            canonical_claims=[
                MemoryCanonicalClaim(
                    path="/items/letter/holder",
                    expected="lin_qiu",
                )
            ],
        ),
        SemanticRecallProbe(
            id="location_rule_20",
            due_section=20,
            category="location_rule",
            required_memory_ids=["memory_location_rule"],
            required_prose=["灯塔地下室禁止明火"],
            canonical_claims=[
                MemoryCanonicalClaim(
                    path="/world/location_rules/lighthouse",
                    expected="地下室禁止明火",
                )
            ],
        ),
        SemanticRecallProbe(
            id="promise_30",
            due_section=30,
            category="promise",
            required_memory_ids=["memory_promise"],
            required_prose=["他们仍须在日出前复核最后一页"],
            canonical_claims=[
                MemoryCanonicalClaim(
                    path="/canonical_facts/promise/status",
                    expected="open",
                )
            ],
        ),
        SemanticRecallProbe(
            id="main_thread_30",
            due_section=30,
            category="main_thread",
            required_memory_ids=["memory_main_thread"],
            required_prose=["他们确认旧信缺失的页码仍是主线线索"],
            canonical_claims=[
                MemoryCanonicalClaim(
                    path="/canonical_facts/main_clue/status",
                    expected="open",
                )
            ],
        ),
    ]


__all__ = [
    "SemanticRecallProbe",
    "SemanticRecallResult",
    "SemanticRecallValidator",
    "recorded_semantic_recall_probes",
]
