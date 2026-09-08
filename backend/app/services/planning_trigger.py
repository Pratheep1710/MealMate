"""MP-032: daily 8 PM sweep trigger calculation for the two planning modes (docs/MP-001,
"Planning modes" — "Same 8 PM daily sweep drives both; trigger offset differs (`grocery_day - 1`
vs. `grocery_day + 1`)"). Reserves triggers the day after grocery_day, once the user has bought
groceries and can report what's available; Suggestion triggers the day before grocery_day, so the
user has lead time to shop from the generated list.

Pure date arithmetic — no DB access, no catalog, no LLM involvement.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

_DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _day_index(day_name: str) -> int:
    try:
        return _DAY_NAMES.index(day_name.lower())
    except ValueError:
        raise ValueError(f"unknown day name: {day_name!r}") from None


@dataclass(frozen=True)
class TriggerDecision:
    should_trigger: bool
    # The grocery_day occurrence this trigger relates to (the day just-passed for Reserves, the
    # day about to arrive for Suggestion). None when should_trigger is False.
    grocery_day_date: datetime.date | None


def compute_trigger(
    sweep_date: datetime.date, grocery_day: str, planning_mode: str
) -> TriggerDecision:
    """Whether `sweep_date`'s 8 PM sweep should trigger generation for a user with the given
    `grocery_day` (day-of-week name, e.g. 'monday') and `planning_mode` ('reserves' | 'suggestion').

    Computed via date subtraction rather than modular weekday arithmetic, so week-boundary cases
    (grocery_day adjacent to Sunday/Monday) fall out correctly without an explicit wraparound
    branch.
    """
    if planning_mode == "reserves":
        offset_days = 1  # trigger is grocery_day + 1
    elif planning_mode == "suggestion":
        offset_days = -1  # trigger is grocery_day - 1
    else:
        raise ValueError(f"unknown planning_mode: {planning_mode!r}")

    candidate_grocery_day_date = sweep_date - datetime.timedelta(days=offset_days)
    should_trigger = candidate_grocery_day_date.weekday() == _day_index(grocery_day)

    return TriggerDecision(
        should_trigger=should_trigger,
        grocery_day_date=candidate_grocery_day_date if should_trigger else None,
    )


def compute_first_plan_start(
    today: datetime.date, grocery_day: str, planning_mode: str
) -> datetime.date:
    """Phase 8 (MP-026): the next date (today included) on which the normal 8 PM sweep would
    trigger generation for this profile — the same day-before/day-after-grocery_day rule
    compute_trigger already encodes above, rolled forward to its nearest occurrence from today.
    Reuses compute_trigger rather than duplicating its day-index arithmetic.

    Equals today when onboarding happens to land exactly on the trigger day; otherwise a concrete
    date up to 6 days out (the mid-week-signup case this function exists to handle correctly). This
    only computes a date to display — it does not itself trigger an immediate generation call; the
    normal scheduled sweep still does that once the returned date arrives.
    """
    for offset in range(7):
        candidate = today + datetime.timedelta(days=offset)
        if compute_trigger(candidate, grocery_day, planning_mode).should_trigger:
            return candidate
    raise AssertionError("unreachable: the trigger day recurs at least once every 7 days")


def week_start_monday(date: datetime.date) -> datetime.date:
    """Phase 9 (MP-094): the Monday of the calendar week containing `date` — mirrors the SQL
    function of the same name (supabase/migrations/0019_plan_item_edit_rpcs.sql's
    week_start_monday) and the one-liner backend/scripts/run_weekly_generation.py's
    _week_start_for_grocery_day already computes ad hoc, given a proper home now that a second
    call site (the live /generation/trigger endpoint) needs the exact same thing.
    """
    return date - datetime.timedelta(days=date.weekday())
