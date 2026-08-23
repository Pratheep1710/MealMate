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
