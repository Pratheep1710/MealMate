"""MP-036: per-day weekly generation context — non-veg constraints, actual target dates, and
prep-bias labels (docs/MP-001 "Time-budget tagging (prep-time bias, weekday vs. weekend) — filter
on existing data, no new functionality", plus user_profiles.nonveg_days_per_week /
nonveg_day_pattern). Feeds MP-034's candidate filtering (blocked on the catalog) with a
deterministic, date-only computation — no catalog or LLM involvement here.

Non-veg constraint rule: when nonveg_day_pattern is set (e.g. {wed, sat}), those named days are
'required' non-veg and every other day is 'veg_only' — the pattern is precise, so days outside it
are pinned veg by the same logic that pinned the named days non-veg. When no pattern is set,
nonveg_days_per_week is a count-only constraint (some N days somewhere in the week) with no
per-day answer yet, so every day is 'flexible' — which day satisfies the count is a generation-time
decision (MP-034/038-044), not this service's job.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Literal

from app.models import UserProfile

_DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WEEKEND_WEEKDAYS = (5, 6)  # Saturday, Sunday, per datetime.date.weekday()

NonvegConstraint = Literal["required", "veg_only", "flexible"]
PrepBias = Literal["quick", "flexible"]


@dataclass(frozen=True)
class DayContext:
    date: datetime.date
    day_name: str
    nonveg_constraint: NonvegConstraint
    prep_bias: PrepBias


@dataclass(frozen=True)
class WeeklyContext:
    week_start: datetime.date
    days: tuple[DayContext, ...]
    nonveg_days_per_week: int


def compute_weekly_context(profile: UserProfile, week_start: datetime.date) -> WeeklyContext:
    """Resolves `week_start` into its 7 concrete calendar dates and computes each day's non-veg
    constraint and prep bias from `profile`. Deterministic: same profile + week_start always
    produces the same result.
    """
    pattern = set(profile.nonveg_day_pattern or [])
    days = tuple(
        _day_context(week_start + datetime.timedelta(days=offset), pattern) for offset in range(7)
    )
    return WeeklyContext(
        week_start=week_start,
        days=days,
        nonveg_days_per_week=profile.nonveg_days_per_week or 0,
    )


def _day_context(date: datetime.date, pattern: set[str]) -> DayContext:
    day_name = _DAY_NAMES[date.weekday()]
    nonveg_constraint: NonvegConstraint
    if not pattern:
        nonveg_constraint = "flexible"
    elif day_name in pattern:
        nonveg_constraint = "required"
    else:
        nonveg_constraint = "veg_only"

    prep_bias: PrepBias = "flexible" if date.weekday() in _WEEKEND_WEEKDAYS else "quick"

    return DayContext(
        date=date, day_name=day_name, nonveg_constraint=nonveg_constraint, prep_bias=prep_bias
    )
