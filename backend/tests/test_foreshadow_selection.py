"""Unit tests for ForeshadowSelectionService.

Covers: eligibility, probability growth, collision resolution,
cooldown, discard, streak unlock, idempotent recovery.
"""

from __future__ import annotations

import pytest

from story.stateful_pipeline.foreshadow_selection import (
    MAX_PROBABILITY,
    ForeshadowSelectionService,
)
from story.stateful_pipeline.models import (
    ForeshadowMode,
    ForeshadowRecord,
    ForeshadowSelectionState,
    ForeshadowStatus,
)


class DeterministicRNG:
    """Injectable RNG for tests."""

    def __init__(self, values: list[float]):
        self._values = list(values)
        self._index = 0

    def random(self) -> float:
        if self._index >= len(self._values):
            return 0.5  # default
        v = self._values[self._index]
        self._index += 1
        return v


def make_foreshadow(
    fid: str = "f1",
    source_chapter: int = 1,
    probability: float = 0.02,
    selected_once: bool = False,
    next_eligible: int = 0,
) -> ForeshadowRecord:
    return ForeshadowRecord(
        id=fid,
        novel_id="test-novel",
        source_chapter=source_chapter,
        summary=f"Foreshadow {fid}",
        current_probability=probability,
        selected_once=selected_once,
        next_eligible_chapter=next_eligible,
    )


def make_state(
    streak: int = 0,
    discard_unlocked: bool = False,
) -> ForeshadowSelectionState:
    return ForeshadowSelectionState(
        novel_id="test-novel",
        consecutive_selection_count=streak,
        discard_unlocked=discard_unlocked,
    )


# ---------------------------------------------------------------------------
# Eligibility Tests
# ---------------------------------------------------------------------------


class TestEligibility:
    def test_too_young(self):
        """Foreshadow at chapter 5, current chapter 12: age=7, not eligible."""
        f = make_foreshadow(source_chapter=5)
        assert not f.is_eligible(12)  # 12-5=7 < 8

    def test_minimum_age_met(self):
        """Foreshadow at chapter 5, current chapter 13: age=8, eligible at 2%."""
        f = make_foreshadow(source_chapter=5)
        assert f.is_eligible(13)  # 13-5=8 >= 8

    def test_selected_once_never_eligible(self):
        """Once selected, never eligible again."""
        f = make_foreshadow(source_chapter=1, selected_once=True)
        assert not f.is_eligible(100)

    def test_in_cooldown(self):
        """Foreshadow in cooldown period not eligible."""
        f = make_foreshadow(source_chapter=1, next_eligible=25)
        assert not f.is_eligible(20)  # 20 < 25
        assert f.is_eligible(25)  # 25 >= 25 and age >= 8

    def test_non_active_status(self):
        """Non-active foreshadows not eligible."""
        f = make_foreshadow(source_chapter=1)
        f.status = ForeshadowStatus.DISCARDED
        assert not f.is_eligible(100)


# ---------------------------------------------------------------------------
# New Foreshadow Count Tests
# ---------------------------------------------------------------------------


class TestNewForeshadowCount:
    def test_fixed_mode(self):
        """Fixed mode always returns the specified count."""
        service = ForeshadowSelectionService(rng=DeterministicRNG([]))
        count, roll = service.determine_new_foreshadow_count(
            ForeshadowMode.FIXED, fixed_count=2
        )
        assert count == 2
        assert roll is None

    def test_fixed_mode_zero(self):
        """Fixed mode with count=0 returns 0."""
        service = ForeshadowSelectionService(rng=DeterministicRNG([]))
        count, roll = service.determine_new_foreshadow_count(
            ForeshadowMode.FIXED, fixed_count=0
        )
        assert count == 0
        assert roll is None

    def test_random_mode_boundaries(self):
        """Test the 80/15/5 distribution boundaries."""
        # roll=0.79 → 0 foreshadows (< 0.80)
        service = ForeshadowSelectionService(rng=DeterministicRNG([0.79]))
        count, roll = service.determine_new_foreshadow_count(ForeshadowMode.RANDOM)
        assert count == 0

        # roll=0.80 → 1 foreshadow (>= 0.80, < 0.95)
        service = ForeshadowSelectionService(rng=DeterministicRNG([0.80]))
        count, roll = service.determine_new_foreshadow_count(ForeshadowMode.RANDOM)
        assert count == 1

        # roll=0.94 → 1 foreshadow
        service = ForeshadowSelectionService(rng=DeterministicRNG([0.94]))
        count, roll = service.determine_new_foreshadow_count(ForeshadowMode.RANDOM)
        assert count == 1

        # roll=0.95 → 2 foreshadows (>= 0.95)
        service = ForeshadowSelectionService(rng=DeterministicRNG([0.95]))
        count, roll = service.determine_new_foreshadow_count(ForeshadowMode.RANDOM)
        assert count == 2

    def test_user_override_fixed_never_random(self):
        """When user sets fixed=2, result must always be 2."""
        for roll in [0.0, 0.5, 0.79, 0.80, 0.95, 0.99]:
            service = ForeshadowSelectionService(rng=DeterministicRNG([roll]))
            count, _ = service.determine_new_foreshadow_count(
                ForeshadowMode.FIXED, fixed_count=2
            )
            assert count == 2, f"fixed=2 must always return 2, got {count} for roll={roll}"


# ---------------------------------------------------------------------------
# Probability Growth Tests
# ---------------------------------------------------------------------------


class TestProbabilityGrowth:
    def test_miss_increases_probability(self):
        """When eligible foreshadow misses, probability += 2%."""
        # roll=0.99 means miss (0.99 >= 0.02)
        rng = DeterministicRNG([0.99])
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.02)
        state = make_state()

        receipt = service.select_foreshadow("test-novel", 15, [f], state)

        assert receipt.collision_winner is None
        assert f.current_probability == pytest.approx(0.04)

    def test_probability_sequence(self):
        """2% → 4% → 6% → 8% on consecutive misses."""
        for expected_p, initial_p in [(0.04, 0.02), (0.06, 0.04), (0.08, 0.06)]:
            rng = DeterministicRNG([0.99])
            service = ForeshadowSelectionService(rng=rng)
            f = make_foreshadow(source_chapter=1, probability=initial_p)
            state = make_state()

            service.select_foreshadow("test-novel", 15, [f], state)
            assert f.current_probability == pytest.approx(expected_p)

    def test_probability_capped_at_100(self):
        """Probability never exceeds 100%."""
        rng = DeterministicRNG([0.99])
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.99)
        state = make_state()

        service.select_foreshadow("test-novel", 15, [f], state)
        assert f.current_probability <= MAX_PROBABILITY

    def test_collision_loser_no_increment(self):
        """Foreshadow that hit but lost collision: probability frozen."""
        # Two foreshadows both hit (roll < prob), collision resolved
        rng = DeterministicRNG([
            0.01,  # f1 hits (0.01 < 0.05)
            0.01,  # f2 hits (0.01 < 0.05)
            0.5,   # collision roll → int(0.5*2)%2 = 1, f2 wins
        ])
        service = ForeshadowSelectionService(rng=rng)
        f1 = make_foreshadow("f1", source_chapter=1, probability=0.05)
        f2 = make_foreshadow("f2", source_chapter=1, probability=0.05)
        state = make_state()

        receipt = service.select_foreshadow("test-novel", 15, [f1, f2], state)

        # f1 lost collision: probability should stay at 0.05
        assert f1.current_probability == pytest.approx(0.05)
        assert "f1" in receipt.cooldown_applied

    def test_cooldown_probability_frozen(self):
        """During cooldown, probability must not change."""
        rng = DeterministicRNG([
            0.01,  # f1 hits
            0.01,  # f2 hits
            0.0,   # collision roll → f1 wins
        ])
        service = ForeshadowSelectionService(rng=rng)
        f1 = make_foreshadow("f1", source_chapter=1, probability=0.18)
        f2 = make_foreshadow("f2", source_chapter=1, probability=0.18)
        state = make_state()

        _receipt = service.select_foreshadow("test-novel", 30, [f1, f2], state)

        # f2 enters cooldown with original probability
        assert f2.current_probability == pytest.approx(0.18)
        assert f2.next_eligible_chapter == 33


# ---------------------------------------------------------------------------
# Collision Resolution Tests
# ---------------------------------------------------------------------------


class TestCollisionResolution:
    def test_single_hit_selected(self):
        """Single hit: directly selected."""
        rng = DeterministicRNG([0.01])  # 0.01 < 0.05 → hit
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)
        state = make_state()

        receipt = service.select_foreshadow("test-novel", 15, [f], state)

        assert receipt.collision_winner == "f1"
        assert f.selected_once is True
        assert f.selected_chapter == 15

    def test_multiple_hits_one_winner(self):
        """Multiple hits: exactly one winner chosen."""
        rng = DeterministicRNG([
            0.01,  # A hits
            0.01,  # B hits
            0.01,  # C hits
            0.4,   # collision roll → index 1 (B)
        ])
        service = ForeshadowSelectionService(rng=rng)
        a = make_foreshadow("A", source_chapter=1, probability=0.05)
        b = make_foreshadow("B", source_chapter=1, probability=0.05)
        c = make_foreshadow("C", source_chapter=1, probability=0.05)
        state = make_state()

        receipt = service.select_foreshadow("test-novel", 15, [a, b, c], state)

        # B wins (index 1 from roll 0.4 * 3 = 1.2 → int = 1)
        assert receipt.collision_winner == "B"
        assert b.selected_once is True
        assert b.selected_chapter == 15

        # A and C lose: cooldown, probability frozen
        assert a.selected_once is False
        assert c.selected_once is False
        assert "A" in receipt.cooldown_applied
        assert "C" in receipt.cooldown_applied

    def test_collision_cooldown_chapters(self):
        """Cooldown lasts exactly 3 chapters."""
        rng = DeterministicRNG([
            0.01,  # A hits
            0.01,  # B hits
            0.0,   # collision → A wins
        ])
        service = ForeshadowSelectionService(rng=rng)
        a = make_foreshadow("A", source_chapter=1, probability=0.05)
        b = make_foreshadow("B", source_chapter=1, probability=0.05)
        state = make_state()

        service.select_foreshadow("test-novel", 30, [a, b], state)

        # B enters cooldown until chapter 33
        assert b.next_eligible_chapter == 33
        assert not b.is_eligible(31)
        assert not b.is_eligible(32)
        assert b.is_eligible(33)

    def test_collision_preserves_original_probability(self):
        """After cooldown, foreshadow resumes with pre-collision probability."""
        rng = DeterministicRNG([
            0.01,  # A hits
            0.01,  # B hits
            0.0,   # collision → A wins
        ])
        service = ForeshadowSelectionService(rng=rng)
        a = make_foreshadow("A", source_chapter=1, probability=0.18)
        b = make_foreshadow("B", source_chapter=1, probability=0.18)
        state = make_state()

        service.select_foreshadow("test-novel", 30, [a, b], state)

        # B's probability stays at 18%, not 20%
        assert b.current_probability == pytest.approx(0.18)


# ---------------------------------------------------------------------------
# Discard Tests
# ---------------------------------------------------------------------------


class TestDiscard:
    def test_no_discard_before_unlock(self):
        """Without discard_unlocked, even low roll doesn't discard."""
        rng = DeterministicRNG([
            0.01,  # foreshadow hits
            0.1,   # would-be discard roll (< 0.25) but unlocked=False
        ])
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)
        state = make_state(streak=0, discard_unlocked=False)

        receipt = service.select_foreshadow("test-novel", 15, [f], state)

        assert receipt.collision_winner == "f1"
        assert receipt.discarded is False
        assert f.discarded is False

    def test_discard_after_unlock(self):
        """After discard_unlocked, 25% chance to discard."""
        rng = DeterministicRNG([
            0.01,  # foreshadow hits
            0.1,   # discard roll (0.1 < 0.25 → discard)
        ])
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)
        state = make_state(streak=3, discard_unlocked=True)

        receipt = service.select_foreshadow("test-novel", 15, [f], state)

        assert receipt.discarded is True
        assert f.discarded is True
        assert f.status == ForeshadowStatus.DISCARDED

    def test_no_discard_high_roll(self):
        """After unlock, high roll means no discard."""
        rng = DeterministicRNG([
            0.01,  # foreshadow hits
            0.9,   # discard roll (0.9 >= 0.25 → keep)
        ])
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)
        state = make_state(streak=3, discard_unlocked=True)

        receipt = service.select_foreshadow("test-novel", 15, [f], state)

        assert receipt.discarded is False
        assert f.discarded is False

    def test_discarded_still_counts_as_selected(self):
        """Discarded foreshadow: selected_once=True, never eligible again."""
        rng = DeterministicRNG([
            0.01,  # hit
            0.1,   # discard
        ])
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)
        state = make_state(streak=3, discard_unlocked=True)

        service.select_foreshadow("test-novel", 15, [f], state)

        assert f.selected_once is True
        assert not f.is_eligible(100)


# ---------------------------------------------------------------------------
# Streak / Unlock Tests
# ---------------------------------------------------------------------------


class TestStreakUnlock:
    def test_streak_increments(self):
        """Consecutive selections increment streak."""
        rng = DeterministicRNG([0.01])
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)
        state = make_state(streak=0)

        service.select_foreshadow("test-novel", 15, [f], state)
        assert state.consecutive_selection_count == 1

    def test_streak_resets_on_miss(self):
        """Missing all foreshadows resets streak."""
        service = ForeshadowSelectionService(rng=DeterministicRNG([0.99]))
        f = make_foreshadow(source_chapter=1, probability=0.02)
        state = make_state(streak=2)

        service.select_foreshadow("test-novel", 15, [f], state)
        assert state.consecutive_selection_count == 0

    def test_unlock_at_three_consecutive(self):
        """Discard unlocks after 3 consecutive selections."""
        state = make_state(streak=2)

        rng = DeterministicRNG([0.01, 0.99])
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)

        service.select_foreshadow("test-novel", 15, [f], state)

        assert state.consecutive_selection_count == 3
        assert state.discard_unlocked is True

    def test_third_selection_not_discarded(self):
        """The selection that reaches 3rd streak is NOT subject to discard."""
        # streak is 2, this selection makes it 3
        rng = DeterministicRNG([0.01, 0.1])  # hit, then would-be discard
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)
        state = make_state(streak=2, discard_unlocked=False)

        receipt = service.select_foreshadow("test-novel", 15, [f], state)

        # This selection unlocks discard but is NOT itself discarded
        assert state.discard_unlocked is True
        assert receipt.discarded is False
        assert f.discarded is False

    def test_unlock_is_permanent(self):
        """Once discard_unlocked=True, never goes back."""
        state = make_state(streak=0, discard_unlocked=True)
        service = ForeshadowSelectionService(rng=DeterministicRNG([0.99]))
        f = make_foreshadow(source_chapter=1, probability=0.02)

        service.select_foreshadow("test-novel", 15, [f], state)

        # Even after missing, unlock stays
        assert state.discard_unlocked is True


# ---------------------------------------------------------------------------
# Idempotent Recovery Tests
# ---------------------------------------------------------------------------


class TestIdempotentRecovery:
    def test_receipt_replay_same_result(self):
        """Replaying a receipt produces identical decisions."""
        rng = DeterministicRNG([0.01, 0.99])
        service = ForeshadowSelectionService(rng=rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)
        state = make_state()

        receipt = service.select_foreshadow("test-novel", 15, [f], state)
        winner = receipt.collision_winner

        # Reset and replay
        f2 = make_foreshadow(source_chapter=1, probability=0.05)
        state2 = make_state()
        replayed = service.select_foreshadow(
            "test-novel", 15, [f2], state2, existing_receipt=receipt
        )

        assert replayed.collision_winner == winner

    def test_no_reroll_on_retry(self):
        """Retry with existing receipt doesn't consume new RNG."""
        initial_rng = DeterministicRNG([0.01])
        service = ForeshadowSelectionService(rng=initial_rng)
        f = make_foreshadow(source_chapter=1, probability=0.05)
        state = make_state()

        receipt = service.select_foreshadow("test-novel", 15, [f], state)

        # Use a completely different RNG for replay
        different_rng = DeterministicRNG([0.99, 0.99, 0.99])
        service2 = ForeshadowSelectionService(rng=different_rng)
        f2 = make_foreshadow(source_chapter=1, probability=0.05)
        state2 = make_state()

        replayed = service2.select_foreshadow(
            "test-novel", 15, [f2], state2, existing_receipt=receipt
        )

        # Same result despite different RNG
        assert replayed.collision_winner == receipt.collision_winner


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_eligible_foreshadows(self):
        """No eligible foreshadows: empty receipt."""
        service = ForeshadowSelectionService(rng=DeterministicRNG([]))
        state = make_state()

        receipt = service.select_foreshadow("test-novel", 5, [], state)

        assert receipt.eligible_foreshadow_ids == []
        assert receipt.collision_winner is None

    def test_all_selected_once(self):
        """All foreshadows already selected: no selection."""
        service = ForeshadowSelectionService(rng=DeterministicRNG([]))
        f = make_foreshadow(source_chapter=1, selected_once=True)
        state = make_state()

        receipt = service.select_foreshadow("test-novel", 15, [f], state)
        assert receipt.collision_winner is None

    def test_mixed_eligible_and_ineligible(self):
        """Only eligible foreshadows participate."""
        rng = DeterministicRNG([0.01])
        service = ForeshadowSelectionService(rng=rng)
        f_young = make_foreshadow("young", source_chapter=10)  # age at ch15 = 5
        f_ready = make_foreshadow("ready", source_chapter=1, probability=0.05)
        state = make_state()

        receipt = service.select_foreshadow("test-novel", 15, [f_young, f_ready], state)

        assert "young" not in receipt.eligible_foreshadow_ids
        assert "ready" in receipt.eligible_foreshadow_ids
