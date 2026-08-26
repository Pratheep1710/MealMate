from __future__ import annotations

import datetime

from scripts.run_weekly_generation import _next_monday


def test_next_monday_is_strictly_after_a_monday_evening_sweep() -> None:
    monday = datetime.date(2026, 8, 24)

    assert _next_monday(monday) == datetime.date(2026, 8, 31)


def test_next_monday_wraps_from_sunday_to_the_following_day() -> None:
    sunday = datetime.date(2026, 8, 30)

    assert _next_monday(sunday) == datetime.date(2026, 8, 31)
