"""Server-owned section budgets and style-compatible stopping rules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from story.narrative_contract import NarrativeModel
from story.writing_plan import SectionWritingPlan


BudgetSegmentName = Literal["opening", "development", "conflict", "resolution"]


class SectionSegmentBudget(NarrativeModel):
    name: BudgetSegmentName
    budget: int = Field(ge=1)
    max_chars: int = Field(ge=1)

    @model_validator(mode="after")
    def maximum_covers_budget(self) -> "SectionSegmentBudget":
        if self.max_chars < self.budget:
            raise ValueError("segment max_chars must cover its budget")
        return self


class StyleBalanceContract(NarrativeModel):
    key: str
    instruction: str
    allowed: list[str] = Field(default_factory=list)
    limits: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class SectionBudgetPlan(NarrativeModel):
    schema_version: int = Field(default=1, ge=1)
    section_id: str = Field(min_length=1)
    target_chars: int = Field(ge=1)
    min_chars: int = Field(ge=1)
    max_chars: int = Field(ge=1)
    segments: list[SectionSegmentBudget] = Field(min_length=4, max_length=4)
    stop_conditions: list[str] = Field(min_length=3)
    style_balance_contract: StyleBalanceContract

    @model_validator(mode="after")
    def validate_range_and_budget(self) -> "SectionBudgetPlan":
        if not self.min_chars <= self.target_chars <= self.max_chars:
            raise ValueError("target_chars must be inside min/max range")
        if sum(item.budget for item in self.segments) != self.target_chars:
            raise ValueError("segment budgets must sum to target_chars")
        return self


_STYLE_BALANCE_CONTRACTS: dict[str, StyleBalanceContract] = {
    "literary": StyleBalanceContract(
        key="literary",
        instruction=(
            "Style controls expression, not structure. Every detail must serve an "
            "existing character, required event, or existing environment."
        ),
        allowed=["event-serving environment", "event-serving interiority", "action detail"],
        limits=["each descriptive beat must connect to the current required action"],
        forbidden=[
            "new scene for literary effect",
            "long description without event function",
            "description after stop conditions",
        ],
    ),
    "noir_cold": StyleBalanceContract(
        key="noir_cold",
        instruction=(
            "Cold does not mean short or omission. Short sentences do not mean a short "
            "chapter. Every required event must show action, decision, and result."
        ),
        allowed=["short sentences", "restrained dialogue", "existing action detail"],
        limits=["low emotion must still fill the server segment budgets"],
        forbidden=["omitting required events", "ending below minimum length"],
    ),
    "warm_healing": StyleBalanceContract(
        key="warm_healing",
        instruction=(
            "Warmth comes from existing characters taking concrete care actions. "
            "Every warm paragraph must advance an existing event, never only emotion."
        ),
        allowed=["care action", "existing-object interaction", "brief response"],
        limits=["at most two consecutive emotional-description paragraphs"],
        forbidden=["repeated emotional explanation", "continued atmosphere after resolution"],
    ),
    "hot_blooded": StyleBalanceContract(
        key="hot_blooded",
        instruction=(
            "Intensity comes only from events already required by the contract. "
            "It may not add enemies, war, casualties, or injuries."
        ),
        allowed=["existing action beats", "existing confrontation dialogue"],
        limits=["stop when the contracted action and end state are complete"],
        forbidden=["new enemy", "war", "casualty", "injury", "new conflict"],
    ),
    "classical_chapter": StyleBalanceContract(
        key="classical_chapter",
        instruction=(
            "Classical expression must come only from language, syntax, and rhythm "
            "around the existing event chain. It may not add historical background."
        ),
        allowed=["cadence", "existing-character dialogue", "existing-scene observation"],
        limits=["all ornament must remain inside the current event"],
        forbidden=["dynasty", "family history", "official title", "date", "new character"],
    ),
}

_GENERIC_BALANCE = StyleBalanceContract(
    key="generic",
    instruction="Use style only inside the existing event chain and stop at completion.",
    allowed=["existing action", "existing environment", "existing-character interaction"],
    limits=["description must serve a required event"],
    forbidden=["new event", "new character", "new background", "post-resolution expansion"],
)


def style_balance_contract(
    style_contract: dict[str, Any] | None,
) -> StyleBalanceContract:
    key = str((style_contract or {}).get("key") or "generic")
    selected = _STYLE_BALANCE_CONTRACTS.get(key, _GENERIC_BALANCE)
    return selected.model_copy(update={"key": key})


class SectionBudgetPlanBuilder:
    """Upgrade a WritingPlan into a centered, capped four-segment budget."""

    _SEGMENTS: tuple[tuple[BudgetSegmentName, float], ...] = (
        ("opening", 0.18),
        ("development", 0.30),
        ("conflict", 0.30),
        ("resolution", 0.22),
    )

    def build(
        self,
        *,
        writing_plan: SectionWritingPlan,
        style_contract: dict[str, Any] | None,
    ) -> SectionBudgetPlan:
        midpoint = (writing_plan.min_chars + writing_plan.max_chars) // 2
        safe_lower = min(writing_plan.max_chars, writing_plan.min_chars + 80)
        safe_upper = max(writing_plan.min_chars, writing_plan.max_chars - 50)
        if safe_lower > safe_upper:
            safe_lower, safe_upper = (
                writing_plan.min_chars,
                writing_plan.max_chars,
            )
        target = max(
            safe_lower,
            min(midpoint + 30, safe_upper),
        )
        budgets: list[int] = []
        used = 0
        for index, (_, ratio) in enumerate(self._SEGMENTS):
            budget = (
                target - used
                if index == len(self._SEGMENTS) - 1
                else round(target * ratio)
            )
            budgets.append(budget)
            used += budget
        segments = [
            SectionSegmentBudget(
                name=name,
                budget=budget,
                max_chars=budget + 50,
            )
            for (name, _), budget in zip(self._SEGMENTS, budgets, strict=True)
        ]
        return SectionBudgetPlan(
            section_id=writing_plan.section_id,
            target_chars=target,
            min_chars=writing_plan.min_chars,
            max_chars=writing_plan.max_chars,
            segments=segments,
            stop_conditions=[
                "required_events_completed",
                "end_state_reached",
                "minimum_length_reached",
            ],
            style_balance_contract=style_balance_contract(style_contract),
        )


def section_budget_plan_prompt_payload(plan: SectionBudgetPlan) -> dict[str, Any]:
    return plan.model_dump(mode="json")


__all__ = [
    "BudgetSegmentName",
    "SectionBudgetPlan",
    "SectionBudgetPlanBuilder",
    "SectionSegmentBudget",
    "StyleBalanceContract",
    "section_budget_plan_prompt_payload",
    "style_balance_contract",
]
