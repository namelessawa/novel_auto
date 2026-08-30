"""Chapter pacing mode selection with hard constraints.

Each chapter draws one pacing mode from a weighted distribution:
  - flat (平淡叙事): weight 6
  - conflict (冲突制造): weight 2
  - climax (高潮): weight 2

Hard constraints enforced by the program (never by LLM):
  - Conflict: at most 1 per 6 consecutive chapters.
  - Climax: at most 1 per 15 consecutive chapters.
  - When conflict is drawn, a 50% roll decides if it resolves in the
    same chapter; otherwise it MUST resolve within 3 chapters.

All random decisions are persisted in a receipt for idempotent recovery.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from story.stateful_pipeline.models import utc_now


class PacingMode(str, Enum):
    FLAT = "flat"
    CONFLICT = "conflict"
    CLIMAX = "climax"


# Weights for the weighted draw. Total = 10.
PACING_WEIGHTS: dict[PacingMode, int] = {
    PacingMode.FLAT: 6,
    PacingMode.CONFLICT: 2,
    PacingMode.CLIMAX: 2,
}
_TOTAL_WEIGHT = sum(PACING_WEIGHTS.values())

# Hard constraint windows.
CONFLICT_WINDOW = 6
CLIMAX_WINDOW = 15
CONFLICT_RESOLUTION_CHANCE = 0.5
CONFLICT_MAX_AGE = 3


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OpenConflict(PipelineModel):
    """A conflict introduced in an earlier chapter that is not yet resolved."""

    introduced_chapter: int = Field(ge=1)
    mode_chapter: int = Field(ge=1)
    deadline_chapter: int = Field(ge=1)
    resolved: bool = False
    resolved_chapter: int | None = None


class PacingState(PipelineModel):
    """Global pacing state for a novel."""

    novel_id: str
    conflict_history: list[int] = Field(default_factory=list)
    climax_history: list[int] = Field(default_factory=list)
    open_conflict: OpenConflict | None = None
    updated_at: str = Field(default_factory=utc_now)

    def conflicts_in_window(self, chapter: int) -> int:
        start = chapter - CONFLICT_WINDOW
        return sum(1 for c in self.conflict_history if c > start)

    def climaxes_in_window(self, chapter: int) -> int:
        start = chapter - CLIMAX_WINDOW
        return sum(1 for c in self.climax_history if c > start)

    def can_use_conflict(self, chapter: int) -> bool:
        return self.conflicts_in_window(chapter) < 1

    def can_use_climax(self, chapter: int) -> bool:
        return self.climaxes_in_window(chapter) < 1


class PacingReceipt(PipelineModel):
    """Persisted random decisions for one chapter's pacing draw."""

    novel_id: str
    chapter: int = Field(ge=1)
    mode_roll: float = Field(ge=0.0, le=1.0)
    selected_mode: PacingMode
    conflict_resolve_roll: float | None = None
    resolve_in_chapter: bool = False
    forced_mode: bool = False
    forced_reason: str = ""
    created_at: str = Field(default_factory=utc_now)


class RNG(Protocol):
    def random(self) -> float: ...


class DefaultRNG:
    def random(self) -> float:
        import random
        return random.random()


class PacingModeSelector:
    """Deterministic pacing mode selector with hard constraints.

    The selector is LLM-free. It draws a mode from the weighted
    distribution, then applies hard constraints (conflict/climax
    windows). If the drawn mode is blocked by a constraint, it falls
    back to flat narration. If there is an unresolved conflict at its
    deadline, the mode is forced to conflict-resolution.
    """

    def __init__(self, rng: RNG | None = None):
        self._rng = rng or DefaultRNG()

    def select_mode(
        self,
        novel_id: str,
        chapter: int,
        state: PacingState,
        existing_receipt: PacingReceipt | None = None,
    ) -> PacingReceipt:
        """Select the pacing mode for a chapter.

        If existing_receipt is provided, replays the same decision
        (idempotent recovery).
        """
        if existing_receipt is not None:
            self._apply_receipt(existing_receipt, state)
            return existing_receipt

        # Forced resolution: an open conflict has reached its deadline.
        if state.open_conflict and not state.open_conflict.resolved:
            if chapter >= state.open_conflict.deadline_chapter:
                receipt = PacingReceipt(
                    novel_id=novel_id,
                    chapter=chapter,
                    mode_roll=0.0,
                    selected_mode=PacingMode.CONFLICT,
                    resolve_in_chapter=True,
                    forced_mode=True,
                    forced_reason="conflict_deadline",
                )
                self._apply_receipt(receipt, state)
                return receipt

        # Weighted draw.
        roll = self._rng.random()
        selected = self._weighted_draw(roll)

        conflict_resolve_roll = None
        resolve_in_chapter = False
        forced = False
        forced_reason = ""

        # Apply hard constraints: fall back to flat if blocked.
        if selected == PacingMode.CONFLICT and not state.can_use_conflict(chapter):
            selected = PacingMode.FLAT
            forced = True
            forced_reason = "conflict_window_full"
        elif selected == PacingMode.CLIMAX and not state.can_use_climax(chapter):
            selected = PacingMode.FLAT
            forced = True
            forced_reason = "climax_window_full"

        # If conflict is selected, roll for same-chapter resolution.
        if selected == PacingMode.CONFLICT:
            conflict_resolve_roll = self._rng.random()
            resolve_in_chapter = conflict_resolve_roll < CONFLICT_RESOLUTION_CHANCE

        receipt = PacingReceipt(
            novel_id=novel_id,
            chapter=chapter,
            mode_roll=roll,
            selected_mode=selected,
            conflict_resolve_roll=conflict_resolve_roll,
            resolve_in_chapter=resolve_in_chapter,
            forced_mode=forced,
            forced_reason=forced_reason,
        )
        self._apply_receipt(receipt, state)
        return receipt

    def _weighted_draw(self, roll: float) -> PacingMode:
        """Map a [0,1) roll onto the weighted distribution."""
        threshold = 0.0
        for mode in (PacingMode.FLAT, PacingMode.CONFLICT, PacingMode.CLIMAX):
            threshold += PACING_WEIGHTS[mode] / _TOTAL_WEIGHT
            if roll < threshold:
                return mode
        return PacingMode.CLIMAX

    def _apply_receipt(self, receipt: PacingReceipt, state: PacingState) -> None:
        """Apply a receipt's decisions to pacing state."""
        chapter = receipt.chapter
        mode = receipt.selected_mode

        if mode == PacingMode.CONFLICT:
            if receipt.resolve_in_chapter:
                # Resolved in the same chapter: record conflict, no open conflict.
                state.conflict_history.append(chapter)
                if state.open_conflict and not state.open_conflict.resolved:
                    state.open_conflict.resolved = True
                    state.open_conflict.resolved_chapter = chapter
                state.open_conflict = None
            else:
                # Opens a conflict that must resolve within 3 chapters.
                state.conflict_history.append(chapter)
                state.open_conflict = OpenConflict(
                    introduced_chapter=chapter,
                    mode_chapter=chapter,
                    deadline_chapter=chapter + CONFLICT_MAX_AGE,
                )
        elif mode == PacingMode.CLIMAX:
            state.climax_history.append(chapter)
            # A climax may also resolve any open conflict.
            if state.open_conflict and not state.open_conflict.resolved:
                state.open_conflict.resolved = True
                state.open_conflict.resolved_chapter = chapter
                state.open_conflict = None

    def resolve_open_conflict(
        self,
        state: PacingState,
        chapter: int,
    ) -> None:
        """Mark the open conflict as resolved (called when prose resolves it)."""
        if state.open_conflict and not state.open_conflict.resolved:
            state.open_conflict.resolved = True
            state.open_conflict.resolved_chapter = chapter
            state.open_conflict = None
