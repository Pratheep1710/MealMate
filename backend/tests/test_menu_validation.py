from __future__ import annotations

import uuid
from dataclasses import replace

from generation_test_helpers import make_context, make_dish, menu_for_context, replace_dish

from app.models import Dish
from app.schemas.weekly_menu import WeeklyMenu
from app.services.menu_validation import validate_menu


def _codes(menu: WeeklyMenu, context) -> set[str]:
    return {issue.code for issue in validate_menu(menu, context).issues}


def test_valid_menu_passes_all_six_rules() -> None:
    context = make_context()
    assert validate_menu(menu_for_context(context), context).is_valid


def test_unknown_dish_fails_candidate_membership() -> None:
    context = make_context()
    menu = menu_for_context(context)
    changed = menu.model_copy(deep=True)
    changed.items[0].dish_id = uuid.uuid4()
    assert "candidate_membership" in _codes(changed, context)


def test_track_variety_dish_cannot_repeat_within_the_output() -> None:
    context = make_context()
    old = context.catalog[0].dishes[0]
    tracked = old.model_copy(update={"track_variety": True})
    context = replace_dish(context, old, tracked)
    menu = menu_for_context(context, include_nonveg=False)
    assert "in_week_repeat" in _codes(menu, context)


def test_recent_track_variety_dish_is_rejected() -> None:
    context = make_context()
    old = context.catalog[0].dishes[1]
    tracked = old.model_copy(update={"track_variety": True})
    context = replace_dish(context, old, tracked)
    context = replace(context, recent_dish_ids=frozenset({tracked.id}))
    assert "recent_repeat" in _codes(menu_for_context(context), context)


def test_combo_template_counts_are_enforced() -> None:
    context = make_context()
    menu = menu_for_context(context)
    items = [item.model_dump() for item in menu.items]
    items = [
        item
        for item in items
        if not (
            item["day"] == context.target_days[0].date
            and item["slot"] == "afternoon"
            and item["item_type"] == "poriyal"
        )
    ]
    changed = WeeklyMenu(week_start=menu.week_start, items=items)
    assert "combo_template" in _codes(changed, context)


def test_night_slot_must_match_the_selected_dinner_style() -> None:
    context = make_context(dinner_style="rice")
    menu = menu_for_context(context)
    changed = menu.model_copy(deep=True)
    night_item = next(item for item in changed.items if item.slot == "night")
    original_diet = context.dishes_by_id[night_item.dish_id].veg_or_nonveg
    tiffin = next(
        dish
        for group in context.catalog
        for dish in group.dishes
        if dish.item_type == "tiffin" and dish.veg_or_nonveg == original_diet
    )
    night_item.item_type = "tiffin"
    night_item.dish_id = tiffin.id

    assert "combo_template" in _codes(changed, context)


def test_dietary_intersection_is_a_hard_reject() -> None:
    context = make_context(restrictions=["Nuts"])
    old = context.catalog[0].dishes[1]
    unsafe = make_dish(
        old.item_type,
        old.veg_or_nonveg,
        dietary_flags=["Nuts"],
        name=old.name,
    )
    context = replace_dish(context, old, unsafe)
    assert "dietary_restriction" in _codes(menu_for_context(context), context)


def test_missing_or_null_dietary_metadata_fails_closed() -> None:
    for missing_kind in ("null", "missing"):
        context = make_context(restrictions=["Nuts"])
        old = context.catalog[0].dishes[1]
        if missing_kind == "null":
            unsafe = old.model_copy(update={"dietary_flags": None})
        else:
            fields = old.model_dump()
            fields.pop("dietary_flags")
            unsafe = Dish.model_construct(**fields)
        context = replace_dish(context, old, unsafe)

        assert "dietary_restriction" in _codes(menu_for_context(context), context)


def test_partial_or_unknown_flag_never_bypasses_safety_metadata_validation() -> None:
    context = make_context(restrictions=["Nuts"])
    old = context.catalog[0].dishes[1]
    malformed = old.model_copy(update={"dietary_flags": ["Nut"]})
    context = replace_dish(context, old, malformed)

    assert "dietary_restriction" in _codes(menu_for_context(context), context)


def test_one_restricted_flag_among_multiple_dish_flags_is_rejected() -> None:
    context = make_context(restrictions=["Nuts"])
    old = context.catalog[0].dishes[1]
    unsafe = old.model_copy(update={"dietary_flags": ["Sesame", "Nuts"]})
    context = replace_dish(context, old, unsafe)

    assert "dietary_restriction" in _codes(menu_for_context(context), context)


def test_any_one_of_multiple_user_restrictions_is_a_hard_reject() -> None:
    context = make_context(restrictions=["Nuts", "Gluten"])
    old = context.catalog[0].dishes[1]
    unsafe = old.model_copy(update={"dietary_flags": ["Gluten"]})
    context = replace_dish(context, old, unsafe)

    assert "dietary_restriction" in _codes(menu_for_context(context), context)


def test_restricted_user_can_receive_a_dish_with_disjoint_valid_flags() -> None:
    context = make_context(restrictions=["Nuts", "Gluten"])
    old = context.catalog[0].dishes[1]
    safe = old.model_copy(update={"dietary_flags": ["Sesame"]})
    context = replace_dish(context, old, safe)

    assert validate_menu(menu_for_context(context), context).is_valid


def test_nonveg_dates_must_match_the_profile_target() -> None:
    context = make_context()
    assert "nonveg_quota" in _codes(menu_for_context(context, include_nonveg=False), context)
