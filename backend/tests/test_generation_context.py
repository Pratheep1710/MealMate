"""Phase 6 generation-context and slot-template tests."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import pytest

from app.models import Dish, UserProfile
from app.services import generation_context
from app.services.generation_context import (
    _evenly_spaced_dates,
    build_generation_catalog,
    build_generation_context,
)
from app.services.slot_templates import GENERATION_ITEM_TYPES, templates_for_profile

_WEEK_START = datetime.date(2026, 8, 24)


def _profile(*, planning_mode: str = "suggestion", dinner_style: str = "rice") -> UserProfile:
    return UserProfile(
        id=uuid.uuid4(),
        nonveg_days_per_week=2,
        nonveg_day_pattern=["wed", "sat"],
        dietary_restrictions=["Nuts"],
        dinner_style=dinner_style,
        planning_mode=planning_mode,
        grocery_day="monday",
        timezone="Asia/Kolkata",
    )


def _dish(item_type: str) -> Dish:
    return Dish(
        id=uuid.uuid4(),
        name=f"{item_type.title()} Dish",
        item_type=item_type,
        veg_or_nonveg="veg",
        region_style="Tamil Nadu",
        prep_minutes=20,
        track_variety=True,
        dietary_flags=[],
    )


def _wire_context_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    profile: UserProfile,
    *,
    recent: set[uuid.UUID] | None = None,
    available: list[uuid.UUID] | None = None,
) -> tuple[list[dict[str, Any]], list[tuple[uuid.UUID, datetime.date]]]:
    catalog_calls: list[dict[str, Any]] = []
    availability_calls: list[tuple[uuid.UUID, datetime.date]] = []

    monkeypatch.setattr(
        generation_context.profiles_repo, "get_profile", lambda conn, user_id: profile
    )
    monkeypatch.setattr(
        generation_context.profiles_repo, "list_favorite_dish_ids", lambda conn, user_id: []
    )
    monkeypatch.setattr(
        generation_context.history_repo, "get_dish_last_used_dates", lambda *args: {}
    )
    monkeypatch.setattr(
        generation_context.history_repo, "get_nonveg_plan_dates", lambda *args: set()
    )

    def get_candidates(conn: object, **kwargs: Any) -> list[Dish]:
        catalog_calls.append(kwargs)
        return [_dish(str(kwargs["item_type"]))]

    def get_available(
        conn: object, user_id: uuid.UUID, week_start: datetime.date
    ) -> list[uuid.UUID]:
        availability_calls.append((user_id, week_start))
        return available or []

    monkeypatch.setattr(generation_context.catalog_repo, "get_candidates", get_candidates)
    monkeypatch.setattr(
        generation_context.catalog_repo,
        "get_reserves_eligible_dish_ids",
        lambda conn, candidate_ids, available_ids: candidate_ids,
    )
    monkeypatch.setattr(
        generation_context, "get_variety_exclusion_set", lambda *args: recent or set()
    )
    monkeypatch.setattr(
        generation_context.availability_repo, "get_available_ingredient_ids", get_available
    )
    return catalog_calls, availability_calls


def test_slot_templates_resolve_the_selected_dinner_style() -> None:
    templates = templates_for_profile(_profile(dinner_style="tiffin"))
    by_slot = {template.slot: template for template in templates}

    assert tuple(item.item_type for item in by_slot["morning"].items) == ("tiffin",)
    assert tuple(item.item_type for item in by_slot["night"].items) == ("tiffin",)
    afternoon = by_slot["afternoon"].items
    assert [(item.item_type, item.minimum, item.maximum) for item in afternoon] == [
        ("rice", 1, 1),
        ("gravy", 1, 2),
        ("poriyal", 1, 1),
    ]


def test_slot_templates_reject_an_unknown_dinner_style() -> None:
    with pytest.raises(ValueError, match="dinner_style"):
        templates_for_profile(_profile(dinner_style="buffet"))


def test_catalog_prefix_is_slot_filtered_but_not_user_filtered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile()
    catalog_calls, _ = _wire_context_dependencies(monkeypatch, profile)

    context = build_generation_context(object(), profile.id, _WEEK_START)  # type: ignore[arg-type]

    assert catalog_calls == [{"item_type": item_type} for item_type in GENERATION_ITEM_TYPES]
    assert tuple(group.item_type for group in context.catalog) == GENERATION_ITEM_TYPES
    assert len(context.candidate_dish_ids) == len(GENERATION_ITEM_TYPES)


def test_catalog_groups_have_deterministic_name_then_id_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile()
    monkeypatch.setattr(
        generation_context.profiles_repo, "get_profile", lambda conn, user_id: profile
    )
    monkeypatch.setattr(
        generation_context.profiles_repo, "list_favorite_dish_ids", lambda conn, user_id: []
    )
    monkeypatch.setattr(
        generation_context.history_repo, "get_dish_last_used_dates", lambda *args: {}
    )
    monkeypatch.setattr(
        generation_context.history_repo, "get_nonveg_plan_dates", lambda *args: set()
    )
    dish_b = _dish("tiffin").model_copy(update={"name": "Zulu"})
    dish_a = _dish("tiffin").model_copy(update={"name": "alpha"})
    monkeypatch.setattr(
        generation_context.catalog_repo,
        "get_candidates",
        lambda conn, **kwargs: [dish_b, dish_a],
    )
    monkeypatch.setattr(generation_context, "get_variety_exclusion_set", lambda *args: set())

    context = build_generation_context(object(), profile.id, _WEEK_START)  # type: ignore[arg-type]

    assert [dish.name for dish in context.catalog[0].dishes] == ["alpha", "Zulu"]


def test_preloaded_catalog_is_reused_without_refetching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile()
    catalog_calls, _ = _wire_context_dependencies(monkeypatch, profile)
    shared_catalog = build_generation_catalog(object())  # type: ignore[arg-type]
    assert len(catalog_calls) == len(GENERATION_ITEM_TYPES)
    catalog_calls.clear()

    context = build_generation_context(  # type: ignore[arg-type]
        object(), profile.id, _WEEK_START, catalog=shared_catalog
    )

    assert context.catalog is shared_catalog
    assert catalog_calls == []


def test_suggestion_mode_never_reads_or_applies_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile(planning_mode="suggestion")
    _, availability_calls = _wire_context_dependencies(
        monkeypatch, profile, available=[uuid.uuid4()]
    )

    context = build_generation_context(object(), profile.id, _WEEK_START)  # type: ignore[arg-type]

    assert availability_calls == []
    assert context.available_ingredient_ids == frozenset()


def test_reserves_mode_reads_the_current_weeks_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile(planning_mode="reserves")
    ingredient_ids = [uuid.uuid4(), uuid.uuid4()]
    _, availability_calls = _wire_context_dependencies(
        monkeypatch, profile, available=ingredient_ids
    )

    context = build_generation_context(object(), profile.id, _WEEK_START)  # type: ignore[arg-type]

    assert availability_calls == [(profile.id, _WEEK_START)]
    assert context.available_ingredient_ids == frozenset(ingredient_ids)


def test_partial_week_starts_on_requested_date_and_uses_it_for_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile()
    excluded_id = uuid.uuid4()
    _wire_context_dependencies(monkeypatch, profile, recent={excluded_id})
    history_calls: list[tuple[uuid.UUID, datetime.date]] = []

    def get_exclusions(conn: object, user_id: uuid.UUID, as_of: datetime.date) -> set[uuid.UUID]:
        history_calls.append((user_id, as_of))
        return {excluded_id}

    monkeypatch.setattr(generation_context, "get_variety_exclusion_set", get_exclusions)
    start_date = _WEEK_START + datetime.timedelta(days=3)

    context = build_generation_context(
        object(),
        profile.id,
        _WEEK_START,
        start_date=start_date,  # type: ignore[arg-type]
    )

    assert context.target_dates == tuple(
        _WEEK_START + datetime.timedelta(days=offset) for offset in range(3, 7)
    )
    assert history_calls == [(profile.id, start_date)]
    assert context.recent_dish_ids == frozenset({excluded_id})


@pytest.mark.parametrize("offset", [-1, 7])
def test_start_date_must_be_inside_the_target_week(offset: int) -> None:
    with pytest.raises(ValueError, match="outside week"):
        build_generation_context(
            object(),  # type: ignore[arg-type]
            uuid.uuid4(),
            _WEEK_START,
            start_date=_WEEK_START + datetime.timedelta(days=offset),
        )


def test_missing_profile_fails_before_catalog_or_history_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generation_context.profiles_repo, "get_profile", lambda conn, user_id: None)

    with pytest.raises(ValueError, match="profile"):
        build_generation_context(object(), uuid.uuid4(), _WEEK_START)  # type: ignore[arg-type]


def test_count_only_nonveg_dates_are_evenly_spaced_and_deterministic() -> None:
    dates = tuple(_WEEK_START + datetime.timedelta(days=offset) for offset in range(7))
    assert _evenly_spaced_dates(dates, 2) == frozenset({dates[1], dates[5]})
    assert _evenly_spaced_dates(dates, 2) == _evenly_spaced_dates(dates, 2)
