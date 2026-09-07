"""Phase 8 brief §0 hard requirement: a profile written by onboarding must produce **identical
exclusion behavior** whether hit via generation (Python, generation_eligibility.py) or via the
Postgres swap RPCs (dish_matches_diet_type / swap_plan_item, 0019+0022 migrations) — same DB, same
profile row, same dish row, both paths asked the same question. Extended (per this session's own
scope decision) beyond Q5 allergies to the new diet_type/meat_types/egg_frequency axis this phase
adds. Integration tests against a real throwaway Postgres database (conftest.py) — skip without one.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from app.models import Dish
from app.repositories import profiles as profiles_repo
from app.services.generation_eligibility import (
    diet_type_allows,
    is_egg_dish,
    normalized_dietary_flags,
)

_DISH_COLUMNS = (
    "id, name, item_type, veg_or_nonveg, region_style, prep_minutes, track_variety, dietary_flags, "
    "meat_type"
)


def _dish(
    conn,
    name: str,
    *,
    item_type: str = "gravy",
    diet: str = "nonveg",
    flags: list[str] | None = None,
    meat_type: str | None = None,
) -> Dish:
    row = conn.execute(
        "insert into dishes "
        "(name, item_type, veg_or_nonveg, dietary_flags, meat_type, track_variety) "
        "values (%s, %s, %s, %s, %s, true) returning " + _DISH_COLUMNS,
        (name, item_type, diet, flags or [], meat_type),
    ).fetchone()
    return Dish.model_validate(row)


def _python_says_ineligible_on_dietary_or_diet_grounds(dish: Dish, profile) -> bool:
    """Mirrors is_eligible's dietary_restrictions + diet_type_allows checks (the two axes this
    cross-check exercises), without needing a full GenerationContext — candidate-membership and
    Reserves-availability aren't part of what either enforcement path is being cross-checked on
    here.
    """
    flags = normalized_dietary_flags(dish)
    if flags is None:
        return True
    if flags & frozenset(profile.dietary_restrictions):
        return True
    return not diet_type_allows(dish, profile)


def _sql_says_dietary_conflict(conn, dish: Dish, profile) -> bool:
    row = conn.execute(
        "select dietary_flags && %s as conflicts from dishes where id = %s",
        (profile.dietary_restrictions, dish.id),
    ).fetchone()
    return bool(row["conflicts"])


def _sql_says_diet_type_mismatch(conn, dish: Dish, user_id: uuid.UUID) -> bool:
    row = conn.execute(
        "select dish_matches_diet_type(%s, %s) as matches", (dish.id, user_id)
    ).fetchone()
    return not row["matches"]


class TestQ5AllergyCrossCheck:
    """Brief §0's explicit requirement: same nut-allergy test case, both paths, must agree."""

    def test_a_nut_allergy_blocks_the_same_dish_via_generation_and_via_swap(
        self, conn, make_user, as_authenticated_user
    ) -> None:
        user_id = make_user()
        conn.execute(
            "update user_profiles set dietary_restrictions = %s where id = %s",
            (["Nuts"], user_id),
        )
        unsafe = _dish(conn, "Peanut Gravy", flags=["Nuts"])
        profile = profiles_repo.get_profile(conn, user_id)
        assert profile is not None

        python_blocks = _python_says_ineligible_on_dietary_or_diet_grounds(unsafe, profile)
        sql_blocks = _sql_says_dietary_conflict(conn, unsafe, profile)

        assert python_blocks is True
        assert sql_blocks is True
        assert python_blocks == sql_blocks

        # And the actual RPC path (not just the predicate) rejects it the same way — same
        # coverage as test_swap_hard_rejects_a_dietary_conflict_not_just_the_happy_path, repeated
        # here so this file stands on its own as the cross-check record the brief asks for.
        safe_dish = _dish(conn, "Safe Placeholder", flags=[])
        item_id = conn.execute(
            "insert into meal_plans (user_id, plan_date, slot) values (%s, '2026-08-24', "
            "'afternoon') returning id",
            (user_id,),
        ).fetchone()["id"]
        item_id = conn.execute(
            "insert into plan_items (plan_id, item_type, dish_id, status) "
            "values (%s, 'gravy', %s, 'filled') returning id",
            (item_id, safe_dish.id),
        ).fetchone()["id"]
        as_authenticated_user(user_id)
        with pytest.raises(psycopg.errors.CheckViolation, match="dietary restrictions"):
            conn.execute("select swap_plan_item(%s, %s)", (item_id, unsafe.id))

    def test_a_safe_dish_is_accepted_by_both_paths(
        self, conn, make_user, as_authenticated_user
    ) -> None:
        user_id = make_user()
        conn.execute(
            "update user_profiles set dietary_restrictions = %s where id = %s",
            (["Nuts"], user_id),
        )
        # veg, so this isolates the allergy check from diet_type_allows (make_user() defaults to
        # diet_type='vegetarian', which would otherwise reject any nonveg dish regardless of flags)
        safe = _dish(conn, "Plain Gravy", diet="veg", flags=[])
        profile = profiles_repo.get_profile(conn, user_id)
        assert profile is not None

        assert _python_says_ineligible_on_dietary_or_diet_grounds(safe, profile) is False
        assert _sql_says_dietary_conflict(conn, safe, profile) is False


class TestDietTypeCrossCheck:
    """New axis this phase adds — same requirement, extended per this session's own scope."""

    def test_vegetarian_rejects_a_chicken_dish_via_both_paths(
        self, conn, make_user, as_authenticated_user
    ) -> None:
        user_id = make_user()  # defaults to diet_type='vegetarian' (0021's own column default)
        chicken = _dish(conn, "Chicken Gravy", meat_type="chicken")
        profile = profiles_repo.get_profile(conn, user_id)
        assert profile is not None
        assert profile.diet_type == "vegetarian"

        assert _python_says_ineligible_on_dietary_or_diet_grounds(chicken, profile) is True
        assert _sql_says_diet_type_mismatch(conn, chicken, user_id) is True

    def test_vegetarian_rejects_an_egg_dish_via_both_paths(
        self, conn, make_user, as_authenticated_user
    ) -> None:
        user_id = make_user()
        egg_dish = _dish(conn, "Egg Curry", flags=["Egg"])
        profile = profiles_repo.get_profile(conn, user_id)
        assert profile is not None
        assert is_egg_dish(egg_dish) is True

        assert _python_says_ineligible_on_dietary_or_diet_grounds(egg_dish, profile) is True
        assert _sql_says_diet_type_mismatch(conn, egg_dish, user_id) is True

    def test_nonvegetarian_with_a_meat_types_restriction_rejects_other_meat_types_via_both_paths(
        self, conn, make_user, as_authenticated_user
    ) -> None:
        user_id = make_user()
        conn.execute(
            "update user_profiles set diet_type = 'nonvegetarian', meat_types = %s, "
            "egg_frequency = 'any', nonveg_days_per_week = 3 where id = %s",
            (["chicken"], user_id),
        )
        mutton = _dish(conn, "Mutton Gravy", meat_type="mutton")
        chicken = _dish(conn, "Chicken Gravy 2", meat_type="chicken")
        profile = profiles_repo.get_profile(conn, user_id)
        assert profile is not None

        assert _python_says_ineligible_on_dietary_or_diet_grounds(mutton, profile) is True
        assert _sql_says_diet_type_mismatch(conn, mutton, user_id) is True
        assert _python_says_ineligible_on_dietary_or_diet_grounds(chicken, profile) is False
        assert _sql_says_diet_type_mismatch(conn, chicken, user_id) is False

    def test_egg_frequency_never_rejects_an_egg_dish_via_both_paths(
        self, conn, make_user, as_authenticated_user
    ) -> None:
        user_id = make_user()
        conn.execute(
            "update user_profiles set diet_type = 'eggetarian', egg_frequency = 'never' "
            "where id = %s",
            (user_id,),
        )
        egg_dish = _dish(conn, "Egg Curry 2", flags=["Egg"])
        profile = profiles_repo.get_profile(conn, user_id)
        assert profile is not None

        assert _python_says_ineligible_on_dietary_or_diet_grounds(egg_dish, profile) is True
        assert _sql_says_diet_type_mismatch(conn, egg_dish, user_id) is True

    def test_eggetarian_accepts_an_egg_dish_via_both_paths_when_frequency_allows_it(
        self, conn, make_user, as_authenticated_user
    ) -> None:
        user_id = make_user()
        conn.execute(
            "update user_profiles set diet_type = 'eggetarian', egg_frequency = 'any' "
            "where id = %s",
            (user_id,),
        )
        egg_dish = _dish(conn, "Egg Curry 3", flags=["Egg"])
        profile = profiles_repo.get_profile(conn, user_id)
        assert profile is not None

        assert _python_says_ineligible_on_dietary_or_diet_grounds(egg_dish, profile) is False
        assert _sql_says_diet_type_mismatch(conn, egg_dish, user_id) is False
