"""Server-owned section structure and style-compatible length planning.

The Writer receives this plan but never decides its structure, event inventory,
or safe expansion dimensions.  All inputs come from already-authoritative
section contracts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from story.event_execution import EventExecutionPlan
from story.narrative_contract import NarrativeContract, NarrativeModel


WritingPartKind = Literal["opening", "development", "conflict", "resolution"]


class WritingPlanPart(NarrativeModel):
    part: WritingPartKind
    target_chars: int = Field(ge=1)
    purpose: str = Field(min_length=1)


class StyleLengthContract(NarrativeModel):
    key: str
    instruction: str
    allowed_expansion: list[str] = Field(default_factory=list)
    forbidden_expansion: list[str] = Field(default_factory=list)


class SectionWritingPlan(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    section_id: str = Field(min_length=1)
    target_chars: int = Field(ge=200, le=10000)
    min_chars: int = Field(ge=1)
    max_chars: int = Field(ge=1)
    structure: list[WritingPlanPart] = Field(min_length=4, max_length=4)
    required_events: list[dict[str, Any]] = Field(default_factory=list)
    required_end_states: list[dict[str, Any]] = Field(default_factory=list)
    style_adaptation: StyleLengthContract


_COMMON_FORBIDDEN = [
    "new event",
    "new character or organization",
    "new background fact or world rule",
    "new number, date, kinship, injury, or casualty",
]

_STYLE_LENGTH_CONTRACTS: dict[str, StyleLengthContract] = {
    "literary": StyleLengthContract(
        key="literary",
        instruction=(
            "Use concrete description, environment, and existing-character interiority "
            "to meet length; do not alter the event chain."
        ),
        allowed_expansion=[
            "environment already present in the scene",
            "sensory observation",
            "existing-character interiority",
            "transitions between required actions",
        ],
        forbidden_expansion=[*_COMMON_FORBIDDEN, "event substitution"],
    ),
    "noir_cold": StyleLengthContract(
        key="noir_cold",
        instruction=(
            "Cold does not mean short. Keep sentences restrained and emotion low, "
            "while meeting length through action, scene observation, dialogue pauses, "
            "and existing-character scrutiny."
        ),
        allowed_expansion=[
            "existing action detail",
            "scene observation",
            "dialogue pause",
            "restrained existing-character reaction",
        ],
        forbidden_expansion=[*_COMMON_FORBIDDEN, "melodramatic emotion"],
    ),
    "warm_healing": StyleLengthContract(
        key="warm_healing",
        instruction=(
            "Meet length through care, existing objects, and existing-character "
            "interaction; required conflict and its outcome may not be removed."
        ),
        allowed_expansion=[
            "care using an existing object",
            "existing-character interaction",
            "sensory comfort already supported by the scene",
            "response after the required conflict",
        ],
        forbidden_expansion=[*_COMMON_FORBIDDEN, "deleting or softening required conflict"],
    ),
    "hot_blooded": StyleLengthContract(
        key="hot_blooded",
        instruction=(
            "Strengthen only actions already required by the contract. Do not invent "
            "war, death, casualty counts, enemies, injuries, or background."
        ),
        allowed_expansion=[
            "beats inside an existing required action",
            "existing-character physical effort without new injury",
            "existing confrontation dialogue",
            "immediate observation of the existing scene",
        ],
        forbidden_expansion=[
            *_COMMON_FORBIDDEN,
            "war, death, new enemy, or casualty count",
            "new injury or escalation outcome",
        ],
    ),
    "classical_chapter": StyleLengthContract(
        key="classical_chapter",
        instruction=(
            "Meet length with cadence, observation, and the existing action chain. "
            "Do not invent history, dynasty, family, office, date, or character."
        ),
        allowed_expansion=[
            "cadence around existing actions",
            "scene observation",
            "existing-character dialogue",
            "transition into the required resolution",
        ],
        forbidden_expansion=[
            *_COMMON_FORBIDDEN,
            "historical background, dynasty, family, office, or date",
        ],
    ),
}

_GENERIC_STYLE = StyleLengthContract(
    key="generic",
    instruction=(
        "Meet length only by elaborating existing action, environment, interaction, "
        "and emotion; do not create plot or facts."
    ),
    allowed_expansion=[
        "existing action detail",
        "existing environment",
        "existing-character interaction",
        "existing-character emotion",
    ],
    forbidden_expansion=_COMMON_FORBIDDEN,
)


def style_length_contract(style_contract: dict[str, Any] | None) -> StyleLengthContract:
    key = str((style_contract or {}).get("key") or "generic")
    selected = _STYLE_LENGTH_CONTRACTS.get(key, _GENERIC_STYLE)
    return selected.model_copy(update={"key": key})


class SectionWritingPlanBuilder:
    """Derive a deterministic four-part plan from frozen section authorities."""

    _PARTS: tuple[tuple[WritingPartKind, float, str], ...] = (
        ("opening", 0.20, "Establish the existing scene and begin the first required action."),
        ("development", 5 / 18, "Develop only the contracted actions and existing interactions."),
        ("conflict", 5 / 18, "Complete the central required action without adding escalation facts."),
        ("resolution", 11 / 45, "Land every required end state explicitly and close the section."),
    )

    def build(
        self,
        *,
        contract: NarrativeContract,
        event_plan: EventExecutionPlan,
        section_goal: Any,
        style_contract: dict[str, Any] | None = None,
    ) -> SectionWritingPlan:
        target = max(
            200,
            min(
                int(section_goal.desired_length),
                int(contract.length_constraint.max_chars),
            ),
        )
        explicit_length = getattr(
            getattr(section_goal, "narrative_constraints", None),
            "length_constraint",
            None,
        )
        minimum = (
            int(contract.length_constraint.min_chars)
            if explicit_length is not None
            else max(int(contract.length_constraint.min_chars), target)
        )
        maximum = (
            int(contract.length_constraint.max_chars)
            if explicit_length is not None
            else min(
                int(contract.length_constraint.max_chars),
                max(minimum, target + 200),
            )
        )
        if maximum < minimum:
            minimum = maximum

        allocated: list[int] = []
        used = 0
        for index, (_, weight, _) in enumerate(self._PARTS):
            chars = target - used if index == len(self._PARTS) - 1 else round(target * weight)
            allocated.append(chars)
            used += chars

        structure = [
            WritingPlanPart(part=part, target_chars=chars, purpose=purpose)
            for (part, _, purpose), chars in zip(self._PARTS, allocated, strict=True)
        ]
        required_events = [
            {
                "id": item.id,
                "order": item.order,
                "actor": item.actor,
                "action": item.action,
                "target": item.target,
                "minimum_completion_evidence": item.minimum_completion_evidence,
            }
            for item in event_plan.ordered_events
            if item.required and not item.allow_omission
        ]
        required_end_states = [
            {
                "id": item.id,
                "path": item.path,
                "expected": item.expected,
                "description": item.description,
            }
            for item in event_plan.required_end_states
        ]
        return SectionWritingPlan(
            section_id=contract.section_id,
            target_chars=target,
            min_chars=minimum,
            max_chars=maximum,
            structure=structure,
            required_events=required_events,
            required_end_states=required_end_states,
            style_adaptation=style_length_contract(style_contract),
        )


def section_writing_plan_prompt_payload(plan: SectionWritingPlan) -> dict[str, Any]:
    return plan.model_dump(mode="json")


__all__ = [
    "SectionWritingPlan",
    "SectionWritingPlanBuilder",
    "StyleLengthContract",
    "WritingPlanPart",
    "section_writing_plan_prompt_payload",
    "style_length_contract",
]
