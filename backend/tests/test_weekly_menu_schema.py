"""MP-037 structured-output schema (app/schemas/weekly_menu.py) — structural validation only.
No business rules (variety/dietary/quota) are tested here; that's MP-041-044's job.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.weekly_menu import WeeklyMenu, WeeklyMenuItem

_WEEK_START = datetime.date(2026, 8, 24)  # a Monday
_SLOTS = ("morning", "afternoon", "night", "snack_1", "snack_2", "snack_3")


def _full_week_items() -> list[dict[str, object]]:
    return [
        {
            "day": _WEEK_START + datetime.timedelta(days=offset),
            "slot": slot,
            "item_type": "rice",
            "dish_id": str(uuid.uuid4()),
        }
        for offset in range(7)
        for slot in _SLOTS
    ]


def test_a_complete_week_validates() -> None:
    menu = WeeklyMenu(week_start=_WEEK_START, items=_full_week_items())
    assert len(menu.items) == 42


def test_missing_slot_is_rejected() -> None:
    items = _full_week_items()[:-1]  # drop the last (day, slot) entry
    with pytest.raises(ValidationError, match="missing"):
        WeeklyMenu(week_start=_WEEK_START, items=items)


def test_a_composed_slot_with_multiple_dishes_validates() -> None:
    # Real lunches are composed: rice + a gravy + poriyal all under the same 'afternoon' slot.
    # plan_items already supports multiple rows per slot — the contract has to allow it too.
    items = _full_week_items()
    lunch_day = _WEEK_START
    items.append(
        {"day": lunch_day, "slot": "afternoon", "item_type": "gravy", "dish_id": str(uuid.uuid4())}
    )
    items.append(
        {
            "day": lunch_day,
            "slot": "afternoon",
            "item_type": "poriyal",
            "dish_id": str(uuid.uuid4()),
        }
    )

    menu = WeeklyMenu(week_start=_WEEK_START, items=items)

    afternoon_items = [i for i in menu.items if i.day == lunch_day and i.slot == "afternoon"]
    assert len(afternoon_items) == 3


def test_a_partial_week_validates_the_start_today_regenerate_path() -> None:
    # docs/MP-001: "Regenerate-remaining-week — reuses the weekly generation path with a
    # start_date argument." Only 3 of the 7 days are present here; each of those 3 is complete.
    partial_days = [_WEEK_START + datetime.timedelta(days=offset) for offset in (2, 3, 4)]
    items = [
        {"day": day, "slot": slot, "item_type": "rice", "dish_id": str(uuid.uuid4())}
        for day in partial_days
        for slot in _SLOTS
    ]

    menu = WeeklyMenu(week_start=_WEEK_START, items=items)

    assert {i.day for i in menu.items} == set(partial_days)


def test_a_present_day_missing_a_slot_is_still_rejected_under_partial_week() -> None:
    partial_days = [_WEEK_START + datetime.timedelta(days=offset) for offset in (2, 3)]
    items = [
        {"day": day, "slot": slot, "item_type": "rice", "dish_id": str(uuid.uuid4())}
        for day in partial_days
        for slot in _SLOTS
    ]
    items.pop()  # drop one slot from the last present day

    with pytest.raises(ValidationError, match="missing"):
        WeeklyMenu(week_start=_WEEK_START, items=items)


def test_empty_items_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WeeklyMenu(week_start=_WEEK_START, items=[])


def test_entry_outside_the_target_week_is_rejected() -> None:
    items = _full_week_items()
    items[0] = {**items[0], "day": _WEEK_START + datetime.timedelta(days=30)}
    with pytest.raises(ValidationError):
        WeeklyMenu(week_start=_WEEK_START, items=items)


def test_invalid_slot_enum_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WeeklyMenuItem(
            day=_WEEK_START, slot="brunch", item_type="rice", dish_id=str(uuid.uuid4())
        )


def test_invalid_item_type_enum_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WeeklyMenuItem(
            day=_WEEK_START, slot="morning", item_type="biryani", dish_id=str(uuid.uuid4())
        )


def test_non_uuid_dish_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WeeklyMenuItem(day=_WEEK_START, slot="morning", item_type="rice", dish_id="not-a-uuid")


def test_missing_required_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WeeklyMenuItem(slot="morning", item_type="rice", dish_id=str(uuid.uuid4()))  # type: ignore[call-arg]


def test_unexpected_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WeeklyMenuItem(
            day=_WEEK_START,
            slot="morning",
            item_type="rice",
            dish_id=str(uuid.uuid4()),
            confidence=0.9,  # type: ignore[call-arg]
        )
