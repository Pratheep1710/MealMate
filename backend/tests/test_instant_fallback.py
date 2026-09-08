"""Phase 9 (MP-093): app/services/instant_fallback.py.

Per the build brief, this must not exercise any new/independent filtering logic — so these tests
reuse the exact adversarial context fixtures already built for Phase 6/8's eligibility gate
(test_menu_validation.py's malformed-dietary-metadata cases, constructed via
generation_test_helpers.make_context/replace_dish) rather than inventing new ones, and drive them
through build_instant_fallback instead of validate_menu/is_eligible directly.
build_generation_context is monkeypatched to hand back the prebuilt context (it's Phase 6
machinery, already covered elsewhere, and calling it for real needs a live Postgres connection
this file has no need for).
"""

from __future__ import annotations

import datetime

import pytest
from generation_test_helpers import WEEK_START, make_context, replace_dish

from app.models import Dish
from app.services import instant_fallback


def _with_context(monkeypatch: pytest.MonkeyPatch, context) -> None:
    monkeypatch.setattr(
        instant_fallback, "build_generation_context", lambda *args, **kwargs: context
    )


def test_missing_or_null_dietary_metadata_is_never_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        _with_context(monkeypatch, context)

        fallback = instant_fallback.build_instant_fallback(
            object(), context.profile.id, WEEK_START
        )

        assert all(item.dish_id != unsafe.id for item in fallback.items)


def test_partial_or_unknown_flag_never_bypasses_safety(monkeypatch: pytest.MonkeyPatch) -> None:
    context = make_context(restrictions=["Nuts"])
    old = context.catalog[0].dishes[1]
    malformed = old.model_copy(update={"dietary_flags": ["Nut"]})
    context = replace_dish(context, old, malformed)
    _with_context(monkeypatch, context)

    fallback = instant_fallback.build_instant_fallback(object(), context.profile.id, WEEK_START)

    assert all(item.dish_id != malformed.id for item in fallback.items)


def test_one_restricted_flag_among_multiple_dish_flags_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(restrictions=["Nuts"])
    old = context.catalog[0].dishes[1]
    unsafe = old.model_copy(update={"dietary_flags": ["Sesame", "Nuts"]})
    context = replace_dish(context, old, unsafe)
    _with_context(monkeypatch, context)

    fallback = instant_fallback.build_instant_fallback(object(), context.profile.id, WEEK_START)

    assert all(item.dish_id != unsafe.id for item in fallback.items)


def test_any_one_of_multiple_user_restrictions_is_a_hard_reject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(restrictions=["Nuts", "Gluten"])
    old = context.catalog[0].dishes[1]
    unsafe = old.model_copy(update={"dietary_flags": ["Gluten"]})
    context = replace_dish(context, old, unsafe)
    _with_context(monkeypatch, context)

    fallback = instant_fallback.build_instant_fallback(object(), context.profile.id, WEEK_START)

    assert all(item.dish_id != unsafe.id for item in fallback.items)


def test_restricted_user_can_still_receive_a_dish_with_disjoint_valid_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context(restrictions=["Nuts", "Gluten"])
    old = context.catalog[0].dishes[1]
    safe = old.model_copy(update={"dietary_flags": ["Sesame"]})
    context = replace_dish(context, old, safe)
    _with_context(monkeypatch, context)

    fallback = instant_fallback.build_instant_fallback(object(), context.profile.id, WEEK_START)

    assert len(fallback.items) > 0


def test_items_are_filtered_to_the_days_ahead_window(monkeypatch: pytest.MonkeyPatch) -> None:
    # make_context's default day_count=2 gives target_days = [Monday, Tuesday]; days_ahead=1
    # should keep only the first of those.
    context = make_context()
    _with_context(monkeypatch, context)

    fallback = instant_fallback.build_instant_fallback(
        object(), context.profile.id, WEEK_START, days_ahead=1
    )

    assert fallback.items
    assert all(item.day == WEEK_START for item in fallback.items)
    assert any(day.date == WEEK_START + datetime.timedelta(days=1) for day in context.target_days)


def test_dishes_by_id_covers_every_selected_item(monkeypatch: pytest.MonkeyPatch) -> None:
    context = make_context()
    _with_context(monkeypatch, context)

    fallback = instant_fallback.build_instant_fallback(object(), context.profile.id, WEEK_START)

    for item in fallback.items:
        if item.dish_id is not None:
            assert item.dish_id in fallback.dishes_by_id
