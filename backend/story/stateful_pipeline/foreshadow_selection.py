"""Deterministic foreshadow selection service.

Implements the complete foreshadow probability state machine:
  - 10-chapter minimum age for eligibility
  - 2% base probability, +2% per missed chapter
  - Independent per-foreshadow roll
  - 1/n collision resolution when multiple hit
  - 3-chapter cooldown for collision losers
  - 25% discard (only after 3-consecutive-selections unlock)
  - Persisted receipts for idempotent recovery

This service is LLM-free and fully deterministic given the same RNG state.
"""

from __future__ import annotations

import random
from typing import Protocol

from story.stateful_pipeline.models import (
    ForeshadowMode,
    ForeshadowRecord,
    ForeshadowSelectionReceipt,
    ForeshadowSelectionState,
    ForeshadowStatus,
    SelectionRollResult,
)

MINIMUM_AGE = 8
BASE_PROBABILITY = 0.02
PROBABILITY_INCREMENT = 0.02
MAX_PROBABILITY = 1.0
COOLDOWN_CHAPTERS = 3
DISCARD_PROBABILITY = 0.25
DISCARD_UNLOCK_THRESHOLD = 3


class RNG(Protocol):
    def random(self) -> float: ...


class DefaultRNG:
    """Standard random RNG for production use."""

    def random(self) -> float:
        return random.random()


class ForeshadowRepository(Protocol):
    """Protocol for foreshadow persistence."""

    def list_active(self, novel_id: str) -> list[ForeshadowRecord]: ...

    def save(self, record: ForeshadowRecord) -> None: ...

    def get_receipt(self, novel_id: str, chapter: int) -> ForeshadowSelectionReceipt | None: ...

    def save_receipt(self, receipt: ForeshadowSelectionReceipt) -> None: ...

    def get_state(self, novel_id: str) -> ForeshadowSelectionState: ...

    def save_state(self, state: ForeshadowSelectionState) -> None: ...


class ForeshadowSelectionService:
    """Pure deterministic foreshadow selection engine.

    All probability logic lives here. LLMs never see or modify this state.
    """

    def __init__(self, rng: RNG | None = None):
        self._rng = rng or DefaultRNG()

    def determine_new_foreshadow_count(
        self,
        mode: ForeshadowMode,
        fixed_count: int = 0,
    ) -> tuple[int, float | None]:
        """Determine how many new foreshadows to extract this chapter.

        Returns (count, roll_value). roll_value is None for fixed mode.
        """
        if mode == ForeshadowMode.FIXED:
            return fixed_count, None

        roll = self._rng.random()
        if roll < 0.80:
            return 0, roll
        elif roll < 0.95:
            return 1, roll
        else:
            return 2, roll

    def select_foreshadow(
        self,
        novel_id: str,
        chapter: int,
        foreshadows: list[ForeshadowRecord],
        state: ForeshadowSelectionState,
        existing_receipt: ForeshadowSelectionReceipt | None = None,
    ) -> ForeshadowSelectionReceipt:
        """Execute the full selection algorithm for a chapter.

        If existing_receipt is provided, replays the same decisions
        (idempotent recovery).
        """
        if existing_receipt is not None:
            return self._replay_receipt(existing_receipt, foreshadows, state)

        receipt = ForeshadowSelectionReceipt(
            novel_id=novel_id,
            chapter=chapter,
        )

        # Step 1: Filter eligible foreshadows
        eligible = [f for f in foreshadows if f.is_eligible(chapter)]
        receipt.eligible_foreshadow_ids = [f.id for f in eligible]

        if not eligible:
            receipt.new_foreshadow_count = 0
            return receipt

        # Step 2: Independent roll for each eligible foreshadow
        hits: list[ForeshadowRecord] = []
        for f in eligible:
            roll_value = self._rng.random()
            hit = roll_value < f.current_probability
            receipt.roll_results.append(
                SelectionRollResult(
                    foreshadow_id=f.id,
                    probability=f.current_probability,
                    roll_value=roll_value,
                    hit=hit,
                )
            )
            if hit:
                hits.append(f)

        # Step 3: Resolve selection
        if not hits:
            # All missed: increment probabilities and reset streak
            self.reset_streak(state)
            for f in eligible:
                increment = min(
                    PROBABILITY_INCREMENT,
                    MAX_PROBABILITY - f.current_probability,
                )
                f.current_probability = min(MAX_PROBABILITY, f.current_probability + PROBABILITY_INCREMENT)
                receipt.probability_increments[f.id] = increment
        elif len(hits) == 1:
            # Single hit: select it
            winner = hits[0]
            receipt.collision_winner = winner.id
            receipt.collision_candidates = [winner.id]
            # Losers get probability increment
            for f in eligible:
                if f.id != winner.id:
                    increment = min(
                        PROBABILITY_INCREMENT,
                        MAX_PROBABILITY - f.current_probability,
                    )
                    f.current_probability = min(MAX_PROBABILITY, f.current_probability + PROBABILITY_INCREMENT)
                    receipt.probability_increments[f.id] = increment
        else:
            # Multiple hits: 1/n collision resolution
            receipt.collision_candidates = [f.id for f in hits]
            collision_roll = self._rng.random()
            receipt.collision_roll = collision_roll
            winner_index = int(collision_roll * len(hits)) % len(hits)
            winner = hits[winner_index]
            receipt.collision_winner = winner.id

            # Losers in collision: freeze probability, apply cooldown
            for f in hits:
                if f.id != winner.id:
                    f.next_eligible_chapter = chapter + COOLDOWN_CHAPTERS
                    receipt.cooldown_applied.append(f.id)

            # Non-hits get probability increment
            hit_ids = {f.id for f in hits}
            for f in eligible:
                if f.id not in hit_ids:
                    increment = min(
                        PROBABILITY_INCREMENT,
                        MAX_PROBABILITY - f.current_probability,
                    )
                    f.current_probability = min(MAX_PROBABILITY, f.current_probability + PROBABILITY_INCREMENT)
                    receipt.probability_increments[f.id] = increment

        # Step 4: Apply discard logic (if winner exists)
        if receipt.collision_winner:
            winner_id = receipt.collision_winner
            # Update state for the winner
            self._apply_selection(
                receipt=receipt,
                winner_id=winner_id,
                foreshadows=foreshadows,
                state=state,
                chapter=chapter,
            )

        return receipt

    def _apply_selection(
        self,
        receipt: ForeshadowSelectionReceipt,
        winner_id: str,
        foreshadows: list[ForeshadowRecord],
        state: ForeshadowSelectionState,
        chapter: int,
    ) -> None:
        """Apply selection consequences to the winner."""
        winner = next((f for f in foreshadows if f.id == winner_id), None)
        if winner is None:
            return

        # Mark as selected
        winner.selected_once = True
        winner.selected_chapter = chapter
        winner.status = ForeshadowStatus.SELECTED

        # Check discard eligibility
        if state.discard_unlocked:
            discard_roll = self._rng.random()
            receipt.discard_roll = discard_roll
            if discard_roll < DISCARD_PROBABILITY:
                receipt.discarded = True
                winner.discarded = True
                winner.status = ForeshadowStatus.DISCARDED

        # Update consecutive selection streak
        state.consecutive_selection_count += 1
        state.last_selected_chapter = chapter

        # Unlock discard after 3 consecutive selections
        if state.consecutive_selection_count >= DISCARD_UNLOCK_THRESHOLD:
            state.discard_unlocked = True

    def reset_streak(self, state: ForeshadowSelectionState) -> None:
        """Reset streak when a chapter selects no foreshadow."""
        state.consecutive_selection_count = 0

    def apply_receipt_to_records(
        self,
        receipt: ForeshadowSelectionReceipt,
        foreshadows: list[ForeshadowRecord],
        state: ForeshadowSelectionState,
    ) -> None:
        """Apply a receipt's decisions to foreshadow records (for recovery)."""
        foreshadow_map = {f.id: f for f in foreshadows}

        # Apply probability increments
        for fid, increment in receipt.probability_increments.items():
            if fid in foreshadow_map:
                foreshadow_map[fid].current_probability = min(
                    MAX_PROBABILITY,
                    foreshadow_map[fid].current_probability + increment,
                )

        # Apply cooldowns
        for fid in receipt.cooldown_applied:
            if fid in foreshadow_map:
                foreshadow_map[fid].next_eligible_chapter = receipt.chapter + COOLDOWN_CHAPTERS

        # Apply winner selection
        if receipt.collision_winner and receipt.collision_winner in foreshadow_map:
            winner = foreshadow_map[receipt.collision_winner]
            winner.selected_once = True
            winner.selected_chapter = receipt.chapter
            winner.status = ForeshadowStatus.SELECTED
            if receipt.discarded:
                winner.discarded = True
                winner.status = ForeshadowStatus.DISCARDED

            state.consecutive_selection_count += 1
            state.last_selected_chapter = receipt.chapter
            if state.consecutive_selection_count >= DISCARD_UNLOCK_THRESHOLD:
                state.discard_unlocked = True
        else:
            # No winner: reset streak
            self.reset_streak(state)

    def _replay_receipt(
        self,
        receipt: ForeshadowSelectionReceipt,
        foreshadows: list[ForeshadowRecord],
        state: ForeshadowSelectionState,
    ) -> ForeshadowSelectionReceipt:
        """Replay an existing receipt (idempotent recovery)."""
        self.apply_receipt_to_records(receipt, foreshadows, state)
        return receipt
