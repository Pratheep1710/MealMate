"""MP-036 weekly context computation (app/services/weekly_context.py) — pure unit tests, no DB
needed.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from pydantic import ValidationError

from app.models import UserProfile
from app.services.weekly_context import compute_weekly_context

_WEEK_START = datetime.date(2026, 8, 24)  # a Monday


def _profile(
    *, nonveg_days_per_week: int | None, nonveg_day_pattern: list[str] | None
) -> UserProfile:
    return UserProfile(
        id=uuid.uuid4(),
        nonveg_days_per_week=nonveg_days_per_week,
        nonveg_day_pattern=nonveg_day_pattern,
        dietary_restrictions=[],
        dinner_style="rice",
        planning_mode="suggestion",
        grocery_day="monday",
        timezone="Asia/Kolkata",
    )


_NO_CONSTRAINTS = _profile(nonveg_days_per_week=None, nonveg_day_pattern=None)


def test_resolves_week_start_into_seven_consecutive_dates() -> None:
    context = compute_weekly_context(_NO_CONSTRAINTS, _WEEK_START)
    dates = [day.date for day in context.days]
    assert dates == [_WEEK_START + datetime.timedelta(days=i) for i in range(7)]
    assert context.week_start == _WEEK_START


def test_pattern_pins_named_days_nonveg_and_the_rest_veg_only() -> None:
    profile = _profile(nonveg_days_per_week=2, nonveg_day_pattern=["wednesday", "saturday"])
    context = compute_weekly_context(profile, _WEEK_START)

    by_name = {day.day_name: day.nonveg_constraint for day in context.days}
    assert by_name["wednesday"] == "required"
    assert by_name["saturday"] == "required"
    for name in ("monday", "tuesday", "thursday", "friday", "sunday"):
        assert by_name[name] == "veg_only"
    assert context.nonveg_days_per_week == 2


def test_pattern_in_the_persisted_abbreviated_form_still_pins_the_right_days() -> None:
    # Regression: 0002_user_profile_favorites_schema.sql's own column comment shows the actually
    # persisted form as {wed, sat} — the abbreviated form, not the full weekday name. Comparing
    # against full names only (as this module used to) silently treats every stored pattern as
    # empty, degrading every day to 'veg_only' instead of the intended 'required' days.
    profile = _profile(nonveg_days_per_week=2, nonveg_day_pattern=["wed", "sat"])
    context = compute_weekly_context(profile, _WEEK_START)

    by_name = {day.day_name: day.nonveg_constraint for day in context.days}
    assert by_name["wednesday"] == "required"
    assert by_name["saturday"] == "required"
    for name in ("monday", "tuesday", "thursday", "friday", "sunday"):
        assert by_name[name] == "veg_only"


def test_pattern_normalization_is_case_insensitive() -> None:
    profile = _profile(nonveg_days_per_week=1, nonveg_day_pattern=["WED"])
    context = compute_weekly_context(profile, _WEEK_START)
    by_name = {day.day_name: day.nonveg_constraint for day in context.days}
    assert by_name["wednesday"] == "required"


def test_a_profile_with_disagreeing_count_and_pattern_cannot_be_constructed() -> None:
    # UserProfile itself rejects this combination (app/models/profile.py) — nonveg_days_per_week=5
    # with a 1-day pattern would otherwise let compute_weekly_context return a WeeklyContext whose
    # nonveg_days_per_week (5) contradicts its own required-day count (1), which no downstream
    # generator or validator could satisfy.
    with pytest.raises(ValidationError, match="nonveg_days_per_week"):
        _profile(nonveg_days_per_week=5, nonveg_day_pattern=["wed"])


def test_the_required_day_count_always_matches_nonveg_days_per_week_when_a_pattern_is_set() -> (
    None
):
    profile = _profile(nonveg_days_per_week=2, nonveg_day_pattern=["wed", "sat"])
    context = compute_weekly_context(profile, _WEEK_START)

    required_count = sum(1 for day in context.days if day.nonveg_constraint == "required")
    assert required_count == context.nonveg_days_per_week


def test_no_pattern_leaves_every_day_flexible() -> None:
    profile = _profile(nonveg_days_per_week=2, nonveg_day_pattern=None)
    context = compute_weekly_context(profile, _WEEK_START)
    assert all(day.nonveg_constraint == "flexible" for day in context.days)
    assert context.nonveg_days_per_week == 2


def test_no_nonveg_days_per_week_defaults_to_zero() -> None:
    context = compute_weekly_context(_NO_CONSTRAINTS, _WEEK_START)
    assert context.nonveg_days_per_week == 0


def test_prep_bias_is_quick_on_weekdays_and_flexible_on_weekends() -> None:
    context = compute_weekly_context(_NO_CONSTRAINTS, _WEEK_START)
    by_name = {day.day_name: day.prep_bias for day in context.days}
    for name in ("monday", "tuesday", "wednesday", "thursday", "friday"):
        assert by_name[name] == "quick"
    for name in ("saturday", "sunday"):
        assert by_name[name] == "flexible"


def test_deterministic_for_the_same_inputs() -> None:
    profile = _profile(nonveg_days_per_week=1, nonveg_day_pattern=["friday"])
    first = compute_weekly_context(profile, _WEEK_START)
    second = compute_weekly_context(profile, _WEEK_START)
    assert first == second
