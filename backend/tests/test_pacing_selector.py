"""Unit tests for PacingModeSelector.

Covers: weighted distribution, conflict/climax window constraints,
conflict resolution deadline, idempotent recovery.
"""

from __future__ import annotations

import pytest

from story.stateful_pipeline.pacing import (
    CLIMAX_WINDOW,
    CONFLICT_MAX_AGE,
    CONFLICT_RESOLUTION_CHANCE,
    CONFLICT_WINDOW,
    PACING_WEIGHTS,
    PacingMode,
    PacingModeSelector,
    PacingReceipt,
    PacingState,
)


class DeterministicRNG:
    def __init__(self, values: list[float]):
        self._values = list(values)
        self._index = 0

    def random(self) -> float:
        if self._index >= len(self._values):
            return 0.5
        v = self._values[self._index]
        self._index += 1
        return v


def make_state(novel_id: str = "test-novel") -> PacingState:
    return PacingState(novel_id=novel_id)


# ---------------------------------------------------------------------------
# Weighted Distribution Tests
# ---------------------------------------------------------------------------


class TestWeightedDraw:
    def test_flat_selected_low_roll(self):
        """roll < 0.6 → flat (weight 6/10)."""
        rng = DeterministicRNG([0.3])
        selector = PacingModeSelector(rng=rng)
        state = make_state()
        receipt = selector.select_mode("test-novel", 1, state)
        assert receipt.selected_mode == PacingMode.FLAT

    def test_conflict_selected_mid_roll(self):
        """0.6 <= roll < 0.8 → conflict (weight 2/10)."""
        rng = DeterministicRNG([0.65, 0.9])  # mode roll, then resolve roll
        selector = PacingModeSelector(rng=rng)
        state = make_state()
        receipt = selector.select_mode("test-novel", 1, state)
        assert receipt.selected_mode == PacingMode.CONFLICT

    def test_climax_selected_high_roll(self):
        """roll >= 0.8 → climax (weight 2/10)."""
        rng = DeterministicRNG([0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()
        receipt = selector.select_mode("test-novel", 1, state)
        assert receipt.selected_mode == PacingMode.CLIMAX

    def test_boundary_flat_to_conflict(self):
        """roll exactly at 0.6 boundary → conflict."""
        rng = DeterministicRNG([0.6, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()
        receipt = selector.select_mode("test-novel", 1, state)
        assert receipt.selected_mode == PacingMode.CONFLICT

    def test_boundary_conflict_to_climax(self):
        """roll exactly at 0.8 boundary → climax."""
        rng = DeterministicRNG([0.8])
        selector = PacingModeSelector(rng=rng)
        state = make_state()
        receipt = selector.select_mode("test-novel", 1, state)
        assert receipt.selected_mode == PacingMode.CLIMAX


# ---------------------------------------------------------------------------
# Conflict Window Constraint Tests
# ---------------------------------------------------------------------------


class TestConflictWindow:
    def test_conflict_blocked_within_window(self):
        """Second conflict within 6 chapters falls back to flat."""
        # First: conflict at chapter 1 (roll 0.65), no same-chapter resolve (0.9)
        rng = DeterministicRNG([0.65, 0.9, 0.65, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        r1 = selector.select_mode("test-novel", 1, state)
        assert r1.selected_mode == PacingMode.CONFLICT

        # Second conflict attempt at chapter 3 (within 6-chapter window)
        r2 = selector.select_mode("test-novel", 3, state)
        assert r2.selected_mode == PacingMode.FLAT
        assert r2.forced_mode is True
        assert r2.forced_reason == "conflict_window_full"

    def test_conflict_allowed_after_window(self):
        """Conflict allowed again after 6 chapters pass."""
        rng = DeterministicRNG([0.65, 0.9, 0.65, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        r1 = selector.select_mode("test-novel", 1, state)
        assert r1.selected_mode == PacingMode.CONFLICT

        # Chapter 8: 8 - 6 = 2, conflict at chapter 1 is outside window (1 <= 2)
        r2 = selector.select_mode("test-novel", 8, state)
        assert r2.selected_mode == PacingMode.CONFLICT

    def test_only_one_conflict_per_window(self):
        """Exactly one conflict allowed per 6-chapter window."""
        rng = DeterministicRNG([0.65, 0.9] * 5)
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        conflict_count = 0
        for chapter in range(1, 7):
            receipt = selector.select_mode("test-novel", chapter, state)
            if receipt.selected_mode == PacingMode.CONFLICT:
                conflict_count += 1

        assert conflict_count == 1


# ---------------------------------------------------------------------------
# Climax Window Constraint Tests
# ---------------------------------------------------------------------------


class TestClimaxWindow:
    def test_climax_blocked_within_window(self):
        """Second climax within 15 chapters falls back to flat."""
        rng = DeterministicRNG([0.9, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        r1 = selector.select_mode("test-novel", 1, state)
        assert r1.selected_mode == PacingMode.CLIMAX

        r2 = selector.select_mode("test-novel", 5, state)
        assert r2.selected_mode == PacingMode.FLAT
        assert r2.forced_mode is True
        assert r2.forced_reason == "climax_window_full"

    def test_climax_allowed_after_window(self):
        """Climax allowed again after 15 chapters pass."""
        rng = DeterministicRNG([0.9, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        r1 = selector.select_mode("test-novel", 1, state)
        assert r1.selected_mode == PacingMode.CLIMAX

        # Chapter 17: 17 - 15 = 2, climax at chapter 1 is outside window
        r2 = selector.select_mode("test-novel", 17, state)
        assert r2.selected_mode == PacingMode.CLIMAX


# ---------------------------------------------------------------------------
# Conflict Resolution Tests
# ---------------------------------------------------------------------------


class TestConflictResolution:
    def test_same_chapter_resolution(self):
        """Conflict with resolve roll < 0.5 resolves in same chapter."""
        rng = DeterministicRNG([0.65, 0.3])  # conflict, resolve (0.3 < 0.5)
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 1, state)
        assert receipt.selected_mode == PacingMode.CONFLICT
        assert receipt.resolve_in_chapter is True
        assert state.open_conflict is None

    def test_deferred_resolution(self):
        """Conflict with resolve roll >= 0.5 opens a 3-chapter deadline."""
        rng = DeterministicRNG([0.65, 0.8])  # conflict, no same-chapter resolve
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 1, state)
        assert receipt.selected_mode == PacingMode.CONFLICT
        assert receipt.resolve_in_chapter is False
        assert state.open_conflict is not None
        assert state.open_conflict.deadline_chapter == 1 + CONFLICT_MAX_AGE

    def test_forced_resolution_at_deadline(self):
        """Open conflict at deadline is forced to resolve."""
        rng = DeterministicRNG([0.65, 0.8])  # conflict, no same-chapter resolve
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        selector.select_mode("test-novel", 1, state)
        assert state.open_conflict is not None
        deadline = state.open_conflict.deadline_chapter

        # At deadline chapter, mode is forced to conflict-resolution
        receipt = selector.select_mode("test-novel", deadline, state)
        assert receipt.selected_mode == PacingMode.CONFLICT
        assert receipt.forced_mode is True
        assert receipt.forced_reason == "conflict_deadline"
        assert receipt.resolve_in_chapter is True
        assert state.open_conflict is None

    def test_manual_resolve_open_conflict(self):
        """resolve_open_conflict clears the open conflict."""
        rng = DeterministicRNG([0.65, 0.8])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        selector.select_mode("test-novel", 1, state)
        assert state.open_conflict is not None

        selector.resolve_open_conflict(state, chapter=2)
        assert state.open_conflict is None


# ---------------------------------------------------------------------------
# Idempotent Recovery Tests
# ---------------------------------------------------------------------------


class TestIdempotentRecovery:
    def test_receipt_replay_same_result(self):
        """Replaying a receipt produces identical mode."""
        rng = DeterministicRNG([0.65, 0.3])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 1, state)
        mode = receipt.selected_mode

        # Replay with different RNG
        different_rng = DeterministicRNG([0.99, 0.99])
        selector2 = PacingModeSelector(rng=different_rng)
        state2 = make_state()
        replayed = selector2.select_mode("test-novel", 1, state2, existing_receipt=receipt)

        assert replayed.selected_mode == mode

    def test_no_reroll_on_retry(self):
        """Retry with existing receipt doesn't consume new RNG."""
        rng = DeterministicRNG([0.65, 0.3])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 1, state)

        # Use empty RNG for replay — should not need any rolls
        empty_rng = DeterministicRNG([])
        selector2 = PacingModeSelector(rng=empty_rng)
        state2 = make_state()
        replayed = selector2.select_mode("test-novel", 1, state2, existing_receipt=receipt)

        assert replayed.selected_mode == receipt.selected_mode


# ---------------------------------------------------------------------------
# Climax Resolves Conflict Tests
# ---------------------------------------------------------------------------


class TestClimaxResolvesConflict:
    def test_climax_resolves_open_conflict(self):
        """A climax also resolves any open conflict."""
        rng = DeterministicRNG([0.65, 0.8, 0.9])  # conflict (deferred), then climax
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        selector.select_mode("test-novel", 1, state)
        assert state.open_conflict is not None

        # Climax at chapter 2 resolves the open conflict
        selector.select_mode("test-novel", 2, state)
        assert state.open_conflict is None
