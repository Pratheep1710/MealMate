"""MP-070: reminder copy composition — pure, no DB/HTTP needed."""

from __future__ import annotations

from app.repositories.plans import DaySlotSummary
from app.services.reminder_copy import compose_reminder


def test_returns_none_when_theres_no_plan_for_the_date():
    assert compose_reminder([]) is None


def test_returns_none_when_theres_no_night_slot():
    day_plan = [DaySlotSummary(slot="morning", is_skipped=False, dish_names=["Idli"])]
    assert compose_reminder(day_plan) is None


def test_uses_dinner_idea_framing_not_plan():
    day_plan = [
        DaySlotSummary(slot="night", is_skipped=False, dish_names=["Steamed Rice", "Sambar"])
    ]

    result = compose_reminder(day_plan)

    assert result is not None
    title, body = result
    assert title == "Tomorrow's dinner idea"
    assert "plan" not in body.lower()
    assert "Steamed Rice" in body and "Sambar" in body


def test_single_dish_night_slot():
    day_plan = [DaySlotSummary(slot="night", is_skipped=False, dish_names=["Curd Rice"])]

    _, body = compose_reminder(day_plan)

    assert body == "Curd Rice"


def test_skipped_night_slot_gets_neutral_copy_not_a_warning():
    day_plan = [DaySlotSummary(slot="night", is_skipped=True, dish_names=[])]

    result = compose_reminder(day_plan)

    assert result is not None
    title, body = result
    assert "incomplete" not in body.lower()
    assert "warning" not in body.lower()


def test_returns_none_when_night_slot_exists_but_has_no_filled_items_yet():
    day_plan = [DaySlotSummary(slot="night", is_skipped=False, dish_names=[])]
    assert compose_reminder(day_plan) is None
