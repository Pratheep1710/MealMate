"""MP-037: structured-output schema for the weekly generation LLM call (docs/MP-001 "Weekly batch
generation (one LLM call/week/user), constrained to a pre-filtered candidate catalog, validated on
6 criteria"). This module is that first, structural gate — day/slot/item_type/dish_id shape and
completeness — not the 6 business criteria themselves (candidate membership, no-repeat, dietary,
quota, etc.), which belong to MP-041-044.

Not wired to an actual OpenAI call — that's MP-040, blocked on `OPENAI_MODEL` being set and on
MP-038/039 (both catalog-blocked). This is the contract only.
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
    """One full week's worth of items. Structural completeness — every (day, slot) pair for the
    7 days starting at `week_start` present exactly once — is enforced here because it's still
    shape, not business logic: it says nothing about *which* dish was picked.
    """

    model_config = ConfigDict(extra="forbid")

    week_start: datetime.date
    items: list[WeeklyMenuItem]

    @model_validator(mode="after")
    def _items_cover_the_week_exactly(self) -> WeeklyMenu:
        expected_days = {
            self.week_start + datetime.timedelta(days=offset)
            for offset in range(_WEEK_LENGTH_DAYS)
        }
        expected_keys = {(day, slot) for day in expected_days for slot in _SLOTS}
        actual_keys = [(item.day, item.slot) for item in self.items]

        if len(actual_keys) != len(set(actual_keys)):
            raise ValueError("duplicate (day, slot) entries in weekly menu items")

        missing = expected_keys - set(actual_keys)
        if missing:
            raise ValueError(f"missing (day, slot) entries: {sorted(missing)}")

        extra = set(actual_keys) - expected_keys
        if extra:
            raise ValueError(f"(day, slot) entries outside the target week: {sorted(extra)}")

        return self
