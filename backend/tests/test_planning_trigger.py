"""MP-032 trigger calculation (app/services/planning_trigger.py) — pure unit tests, no DB needed.

Dates below are anchored to the week of 2026-08-23 (a Sunday) through 2026-08-29 (a Saturday), so
each case's day-of-week is explicit without relying on datetime.date.strftime() at test-definition
time.
"""

from __future__ import annotations

import datetime

import pytest

from app.services.planning_trigger import (
    compute_first_plan_start,
    compute_trigger,
    week_start_monday,
)

_SUNDAY = datetime.date(2026, 8, 23)
_MONDAY = datetime.date(2026, 8, 24)
_TUESDAY = datetime.date(2026, 8, 25)
_WEDNESDAY = datetime.date(2026, 8, 26)
_THURSDAY = datetime.date(2026, 8, 27)
_FRIDAY = datetime.date(2026, 8, 28)


@pytest.mark.parametrize(
    ("sweep_date", "grocery_day", "planning_mode", "expected_grocery_day_date"),
    [
        # Mid-week, no wraparound.
        (_THURSDAY, "wednesday", "reserves", _WEDNESDAY),
        (_TUESDAY, "wednesday", "suggestion", _WEDNESDAY),
        # Week-boundary wraparound: grocery_day is Sunday, reserves trigger day is Monday —
        # weekday index wraps 6 -> 0.
        (_MONDAY, "sunday", "reserves", _SUNDAY),
        # Week-boundary wraparound: grocery_day is Monday, suggestion trigger day is Sunday —
        # weekday index wraps 0 -> 6.
        (_SUNDAY, "monday", "suggestion", _MONDAY),
    ],
)
def test_trigger_fires_on_the_correct_offset_day(
    sweep_date: datetime.date,
    grocery_day: str,
    planning_mode: str,
    expected_grocery_day_date: datetime.date,
) -> None:
    result = compute_trigger(sweep_date, grocery_day, planning_mode)
    assert result.should_trigger is True
    assert result.grocery_day_date == expected_grocery_day_date


@pytest.mark.parametrize(
    ("sweep_date", "grocery_day", "planning_mode"),
    [
        (_WEDNESDAY, "wednesday", "reserves"),  # grocery day itself, not the day after
        (_WEDNESDAY, "wednesday", "suggestion"),  # grocery day itself, not the day before
        (_THURSDAY, "wednesday", "suggestion"),  # off by two days in the wrong direction
        (_SUNDAY, "sunday", "reserves"),  # grocery day itself, wraparound case
    ],
)
def test_trigger_does_not_fire_on_other_days(
    sweep_date: datetime.date, grocery_day: str, planning_mode: str
) -> None:
    result = compute_trigger(sweep_date, grocery_day, planning_mode)
    assert result.should_trigger is False
    assert result.grocery_day_date is None


def test_unknown_planning_mode_raises() -> None:
    with pytest.raises(ValueError, match="planning_mode"):
        compute_trigger(_MONDAY, "monday", "biweekly")


def test_unknown_day_name_raises() -> None:
    with pytest.raises(ValueError, match="day name"):
        compute_trigger(_MONDAY, "funday", "reserves")


# Phase 8 (MP-026): compute_first_plan_start — pure unit tests, no DB needed.


def test_signing_up_exactly_on_the_trigger_day_returns_today() -> None:
    # Suggestion triggers grocery_day - 1: signing up on Friday with grocery_day=Saturday means
    # today already *is* the trigger day.
    assert compute_first_plan_start(_FRIDAY, "saturday", "suggestion") == _FRIDAY


def test_mid_week_signup_in_suggestion_mode_returns_the_upcoming_trigger_day() -> None:
    # This is the scenario MP-026 exists to handle correctly: a Tuesday signup with a Saturday
    # grocery_day doesn't return "today" — it returns the concrete upcoming Friday (grocery_day -
    # 1), several days out, not immediate.
    assert compute_first_plan_start(_TUESDAY, "saturday", "suggestion") == _FRIDAY


def test_mid_week_signup_in_reserves_mode_returns_the_upcoming_trigger_day() -> None:
    # Reserves triggers grocery_day + 1: same Tuesday signup, Saturday grocery_day. The Sunday
    # right after this Saturday (Aug 23) already passed relative to this Tuesday (Aug 25), so the
    # next occurrence is a full week out — Aug 30, not Aug 23.
    expected = _SUNDAY + datetime.timedelta(days=7)
    assert compute_first_plan_start(_TUESDAY, "saturday", "reserves") == expected


def test_first_plan_start_wraps_correctly_across_a_week_boundary() -> None:
    # grocery_day=Monday, Suggestion triggers the day before (Sunday) — starting from a Monday
    # itself must roll all the way to the *next* Sunday, not "yesterday".
    expected = _SUNDAY + datetime.timedelta(days=7)
    assert compute_first_plan_start(_MONDAY, "monday", "suggestion") == expected


def test_first_plan_start_never_looks_more_than_six_days_out() -> None:
    for planning_mode in ("suggestion", "reserves"):
        for grocery_day in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ):
            result = compute_first_plan_start(_WEDNESDAY, grocery_day, planning_mode)
            assert _WEDNESDAY <= result <= _WEDNESDAY + datetime.timedelta(days=6)


# Phase 9 (MP-094): week_start_monday — pure date arithmetic, no DB needed.


def test_week_start_monday_of_a_date_already_on_monday_is_itself() -> None:
    assert week_start_monday(_MONDAY) == _MONDAY


def test_week_start_monday_rolls_a_mid_week_date_back_to_its_monday() -> None:
    assert week_start_monday(_WEDNESDAY) == _MONDAY


def test_week_start_monday_rolls_sunday_back_to_the_preceding_monday() -> None:
    assert week_start_monday(_SUNDAY) == _MONDAY - datetime.timedelta(days=7)
