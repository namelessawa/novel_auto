from __future__ import annotations

from story.chapter_plan import ChapterPlanBuilder
from story.chapter_plan_validator import ChapterPlanValidator
from tests.test_chapter_plan import plan_authorities


def _validated(**updates):
    event_plan, budget_plan = plan_authorities()
    plan = ChapterPlanBuilder().build(
        event_plan=event_plan,
        budget_plan=budget_plan,
    ).model_copy(update=updates)
    report = ChapterPlanValidator().validate(
        plan=plan,
        event_plan=event_plan,
        budget_plan=budget_plan,
    )
    return report, plan


def test_valid_plan_passes() -> None:
    report, _ = _validated()

    assert report.accepted is True
    assert report.required_event_count == report.covered_event_count == 2
    assert report.required_end_state_count == report.covered_end_state_count == 1


def test_missing_event_is_rejected() -> None:
    _, plan = _validated()
    segments = [
        item.model_copy(update={"events": []})
        if "handover" in item.events
        else item
        for item in plan.segments
    ]
    report, _ = _validated(segments=segments)

    assert report.accepted is False
    assert "PLAN_EVENT_MISSING" in {item.code for item in report.violations}


def test_missing_end_state_is_rejected() -> None:
    report, _ = _validated(required_end_states=[])

    assert report.accepted is False
    assert "PLAN_END_STATE_MISSING" in {
        item.code for item in report.violations
    }


def test_segment_budget_must_equal_target() -> None:
    _, plan = _validated()
    segments = [
        plan.segments[0].model_copy(
            update={"target_chars": plan.segments[0].target_chars + 1}
        ),
        *plan.segments[1:],
    ]
    report, _ = _validated(segments=segments)

    assert "PLAN_BUDGET_MISMATCH" in {
        item.code for item in report.violations
    }


def test_extra_character_is_rejected() -> None:
    _, plan = _validated()
    segments = [
        plan.segments[0].model_copy(
            update={"events": [*plan.segments[0].events, "character:new_person"]}
        ),
        *plan.segments[1:],
    ]
    report, _ = _validated(segments=segments)

    assert "PLAN_EXTRA_CHARACTER" in {
        item.code for item in report.violations
    }


def test_extra_location_is_rejected() -> None:
    _, plan = _validated()
    segments = [
        plan.segments[0].model_copy(
            update={"events": [*plan.segments[0].events, "location:new_place"]}
        ),
        *plan.segments[1:],
    ]
    report, _ = _validated(segments=segments)

    assert "PLAN_EXTRA_LOCATION" in {
        item.code for item in report.violations
    }
