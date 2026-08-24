"""MP-032 trigger calculation (app/services/planning_trigger.py) — pure unit tests, no DB needed.

Dates below are anchored to the week of 2026-08-23 (a Sunday) through 2026-08-29 (a Saturday), so
each case's day-of-week is explicit without relying on datetime.date.strftime() at test-definition
time.
"""

from __future__ import annotations

import datetime

import pytest

from app.services.planning_trigger import compute_trigger

_SUNDAY = datetime.date(2026, 8, 23)
_MONDAY = datetime.date(2026, 8, 24)
_TUESDAY = datetime.date(2026, 8, 25)
_WEDNESDAY = datetime.date(2026, 8, 26)
_THURSDAY = datetime.date(2026, 8, 27)


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
