"""Unit tests for PacingModeSelector.

Covers: weighted distribution, conflict/climax window constraints,
conflict resolution deadline, idempotent recovery.
"""

from __future__ import annotations


from story.stateful_pipeline.pacing import (
    CONFLICT_MAX_AGE,
    PacingMode,
    PacingModeSelector,
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
        """0.6 <= roll < 0.8 → conflict (weight 2/10). Uses chapter >= 16."""
        rng = DeterministicRNG([0.65, 0.9])  # mode roll, then resolve roll
        selector = PacingModeSelector(rng=rng)
        state = make_state()
        receipt = selector.select_mode("test-novel", 16, state)
        assert receipt.selected_mode == PacingMode.CONFLICT

    def test_climax_selected_high_roll(self):
        """roll >= 0.8 → climax (weight 2/10). Uses chapter >= 21."""
        rng = DeterministicRNG([0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()
        receipt = selector.select_mode("test-novel", 21, state)
        assert receipt.selected_mode == PacingMode.CLIMAX

    def test_boundary_flat_to_conflict(self):
        """roll exactly at 0.6 boundary → conflict. Uses chapter >= 16."""
        rng = DeterministicRNG([0.6, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()
        receipt = selector.select_mode("test-novel", 16, state)
        assert receipt.selected_mode == PacingMode.CONFLICT

    def test_boundary_conflict_to_climax(self):
        """roll exactly at 0.8 boundary → climax. Uses chapter >= 21."""
        rng = DeterministicRNG([0.8])
        selector = PacingModeSelector(rng=rng)
        state = make_state()
        receipt = selector.select_mode("test-novel", 21, state)
        assert receipt.selected_mode == PacingMode.CLIMAX


# ---------------------------------------------------------------------------
# Conflict Window Constraint Tests
# ---------------------------------------------------------------------------


class TestConflictWindow:
    def test_conflict_blocked_within_window(self):
        """Second conflict within 6 chapters falls back to flat."""
        # First: conflict at chapter 16 (roll 0.65), no same-chapter resolve (0.9)
        rng = DeterministicRNG([0.65, 0.9, 0.65, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        r1 = selector.select_mode("test-novel", 16, state)
        assert r1.selected_mode == PacingMode.CONFLICT

        # Second conflict attempt at chapter 18 (within 6-chapter window, 18-16=2)
        r2 = selector.select_mode("test-novel", 18, state)
        assert r2.selected_mode == PacingMode.FLAT
        assert r2.forced_mode is True
        assert r2.forced_reason == "conflict_window_full"

    def test_conflict_allowed_after_window(self):
        """Conflict allowed again after 6 chapters pass."""
        rng = DeterministicRNG([0.65, 0.9, 0.65, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        r1 = selector.select_mode("test-novel", 16, state)
        assert r1.selected_mode == PacingMode.CONFLICT

        # Chapter 23: 23 - 6 = 17, conflict at chapter 16 is outside window (16 <= 17)
        r2 = selector.select_mode("test-novel", 23, state)
        assert r2.selected_mode == PacingMode.CONFLICT

    def test_only_one_conflict_per_window(self):
        """Exactly one conflict introduced per 6-chapter window.

        Forced deadline resolutions (forced_mode=True) close an existing
        conflict and are not counted as new introductions.
        """
        rng = DeterministicRNG([0.65, 0.9] * 5)
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        conflict_count = 0
        for chapter in range(16, 22):
            receipt = selector.select_mode("test-novel", chapter, state)
            if receipt.selected_mode == PacingMode.CONFLICT and not receipt.forced_mode:
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

        r1 = selector.select_mode("test-novel", 21, state)
        assert r1.selected_mode == PacingMode.CLIMAX

        r2 = selector.select_mode("test-novel", 25, state)
        assert r2.selected_mode == PacingMode.FLAT
        assert r2.forced_mode is True
        assert r2.forced_reason == "climax_window_full"

    def test_climax_allowed_after_window(self):
        """Climax allowed again after 15 chapters pass."""
        rng = DeterministicRNG([0.9, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        r1 = selector.select_mode("test-novel", 21, state)
        assert r1.selected_mode == PacingMode.CLIMAX

        # Chapter 37: 37 - 15 = 22, climax at chapter 21 is outside window (21 <= 22)
        r2 = selector.select_mode("test-novel", 37, state)
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

        receipt = selector.select_mode("test-novel", 16, state)
        assert receipt.selected_mode == PacingMode.CONFLICT
        assert receipt.resolve_in_chapter is True
        assert state.open_conflict is None

    def test_deferred_resolution(self):
        """Conflict with resolve roll >= 0.5 opens a 3-chapter deadline."""
        rng = DeterministicRNG([0.65, 0.8])  # conflict, no same-chapter resolve
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 16, state)
        assert receipt.selected_mode == PacingMode.CONFLICT
        assert receipt.resolve_in_chapter is False
        assert state.open_conflict is not None
        assert state.open_conflict.deadline_chapter == 16 + CONFLICT_MAX_AGE

    def test_forced_resolution_at_deadline(self):
        """Open conflict at deadline is forced to resolve."""
        rng = DeterministicRNG([0.65, 0.8])  # conflict, no same-chapter resolve
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        selector.select_mode("test-novel", 16, state)
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

        selector.select_mode("test-novel", 16, state)
        assert state.open_conflict is not None

        selector.resolve_open_conflict(state, chapter=17)
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

        receipt = selector.select_mode("test-novel", 16, state)
        mode = receipt.selected_mode

        # Replay with different RNG
        different_rng = DeterministicRNG([0.99, 0.99])
        selector2 = PacingModeSelector(rng=different_rng)
        state2 = make_state()
        replayed = selector2.select_mode("test-novel", 16, state2, existing_receipt=receipt)

        assert replayed.selected_mode == mode

    def test_no_reroll_on_retry(self):
        """Retry with existing receipt doesn't consume new RNG."""
        rng = DeterministicRNG([0.65, 0.3])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 16, state)

        # Use empty RNG for replay — should not need any rolls
        empty_rng = DeterministicRNG([])
        selector2 = PacingModeSelector(rng=empty_rng)
        state2 = make_state()
        replayed = selector2.select_mode("test-novel", 16, state2, existing_receipt=receipt)

        assert replayed.selected_mode == receipt.selected_mode


# ---------------------------------------------------------------------------
# Climax Resolves Conflict Tests
# ---------------------------------------------------------------------------


class TestClimaxResolvesConflict:
    def test_climax_resolves_open_conflict(self):
        """A climax also resolves any open conflict."""
        # Conflict at chapter 19 (deferred, deadline = 22), climax at chapter 21.
        rng = DeterministicRNG([0.65, 0.8, 0.9])  # conflict (deferred), then climax
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        selector.select_mode("test-novel", 19, state)
        assert state.open_conflict is not None
        assert state.open_conflict.deadline_chapter == 22

        # Climax at chapter 21 (before deadline 22) resolves the open conflict
        selector.select_mode("test-novel", 21, state)
        assert state.open_conflict is None


# ---------------------------------------------------------------------------
# Earliest Chapter Constraint Tests
# ---------------------------------------------------------------------------


class TestEarliestChapter:
    def test_conflict_blocked_before_chapter_16(self):
        """Conflict drawn before chapter 16 falls back to flat."""
        rng = DeterministicRNG([0.65, 0.9])  # would be conflict
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 15, state)
        assert receipt.selected_mode == PacingMode.FLAT
        assert receipt.forced_mode is True
        assert receipt.forced_reason == "conflict_too_early"

    def test_conflict_allowed_at_chapter_16(self):
        """Conflict allowed exactly at chapter 16."""
        rng = DeterministicRNG([0.65, 0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 16, state)
        assert receipt.selected_mode == PacingMode.CONFLICT

    def test_climax_blocked_before_chapter_21(self):
        """Climax drawn before chapter 21 falls back to flat."""
        rng = DeterministicRNG([0.9])  # would be climax
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 20, state)
        assert receipt.selected_mode == PacingMode.FLAT
        assert receipt.forced_mode is True
        assert receipt.forced_reason == "climax_too_early"

    def test_climax_allowed_at_chapter_21(self):
        """Climax allowed exactly at chapter 21."""
        rng = DeterministicRNG([0.9])
        selector = PacingModeSelector(rng=rng)
        state = make_state()

        receipt = selector.select_mode("test-novel", 21, state)
        assert receipt.selected_mode == PacingMode.CLIMAX

    def test_early_chapters_always_flat(self):
        """Chapters 1-15 always flat regardless of roll."""
        selector = PacingModeSelector(rng=DeterministicRNG([0.99] * 15))
        state = make_state()

        for chapter in range(1, 16):
            receipt = selector.select_mode("test-novel", chapter, state)
            assert receipt.selected_mode == PacingMode.FLAT, (
                f"Chapter {chapter} should be flat"
            )
