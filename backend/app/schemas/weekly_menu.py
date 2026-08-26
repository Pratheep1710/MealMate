"""MP-037: structured-output schema for the weekly generation LLM call (docs/MP-001 "Weekly batch
generation (one LLM call/week/user), constrained to a pre-filtered candidate catalog, validated on
6 criteria"). This module is that first, structural gate — day/slot/item_type/dish_id shape and
completeness — not the 6 business criteria themselves (candidate membership, no-repeat, dietary,
quota, etc.), which belong to MP-041-044.

Phase 6 wires this contract to the OpenAI Responses API in
app/services/openai_generation.py; the six business checks remain in menu_validation.py.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Slot = Literal["morning", "afternoon", "night", "snack_1", "snack_2", "snack_3"]
ItemType = Literal["tiffin", "rice", "gravy", "poriyal", "kootu", "curd", "snack", "sweet"]

_SLOTS: tuple[Slot, ...] = ("morning", "afternoon", "night", "snack_1", "snack_2", "snack_3")
_WEEK_LENGTH_DAYS = 7


class WeeklyMenuItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: datetime.date
    slot: Slot
    item_type: ItemType
    dish_id: uuid.UUID


class WeeklyMenu(BaseModel):
    """A week's (or partial week's, for the regenerate-remaining-week path, docs/MP-001) worth of
    items. Structural completeness is enforced here because it's still shape, not business logic —
    it says nothing about *which* dish was picked:

    - Every `day` present must fall within the 7 days starting at `week_start`.
    - Every `day` present must have all 6 slots represented at least once — but a slot may appear
      more than once, since a real slot is often composed of several dishes (e.g. lunch = rice +
      a gravy + poriyal; `plan_items` already supports multiple rows per slot). Uniqueness at the
      (day, slot) level would reject exactly the composed-slot shape the schema needs to represent.
    - Not every one of the 7 days needs to be present — regenerating only the remaining days of an
      in-progress week is a valid, narrower call to this same contract.
    """

    model_config = ConfigDict(extra="forbid")

    week_start: datetime.date
    items: list[WeeklyMenuItem]

    @model_validator(mode="after")
    def _items_are_structurally_complete(self) -> WeeklyMenu:
        if not self.items:
            raise ValueError("weekly menu must contain at least one item")

        valid_days = {
            self.week_start + datetime.timedelta(days=offset)
            for offset in range(_WEEK_LENGTH_DAYS)
        }
        out_of_range = {item.day for item in self.items if item.day not in valid_days}
        if out_of_range:
            raise ValueError(f"day(s) outside the target week: {sorted(out_of_range)}")

        slots_by_day: dict[datetime.date, set[Slot]] = {}
        for item in self.items:
            slots_by_day.setdefault(item.day, set()).add(item.slot)

        for day, slots in sorted(slots_by_day.items()):
            missing_slots = set(_SLOTS) - slots
            if missing_slots:
                raise ValueError(f"{day} is missing slot(s): {sorted(missing_slots)}")

        return self
