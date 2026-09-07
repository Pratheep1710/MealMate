"""Phase 8 (MP-024): diet_type_allows — the hard diet-identity gate
(app/services/generation_eligibility.py) — pure unit tests, no DB or GenerationContext needed.
"""

from __future__ import annotations

import uuid

from generation_test_helpers import make_dish

from app.models import UserProfile
from app.services.generation_eligibility import diet_type_allows, is_egg_dish


def _profile(
    *,
    diet_type: str,
    meat_types: list[str] | None = None,
    egg_frequency: str | None,
    nonveg_days_per_week: int | None = None,
) -> UserProfile:
    return UserProfile(
        id=uuid.uuid4(),
        nonveg_days_per_week=nonveg_days_per_week,
        nonveg_day_pattern=None,
        dietary_restrictions=[],
        dinner_style="rice",
        planning_mode="suggestion",
        grocery_day="monday",
        timezone="Asia/Kolkata",
        diet_type=diet_type,
        meat_types=meat_types or [],
        egg_frequency=egg_frequency,
        egg_day_pattern=[],
        allergy_other_text=None,
    )


def _egg_dish():
    return make_dish("tiffin", "nonveg", dietary_flags=["Egg"], meat_type=None)


def _meat_dish(meat_type: str | None):
    return make_dish("gravy", "nonveg", dietary_flags=[], meat_type=meat_type)


def _veg_dish():
    return make_dish("poriyal", "veg")


def test_veg_dish_is_always_allowed() -> None:
    for diet_type, egg_frequency in (
        ("vegetarian", None),
        ("eggetarian", "any"),
        ("nonvegetarian", "any"),
    ):
        profile = _profile(diet_type=diet_type, egg_frequency=egg_frequency)
        assert diet_type_allows(_veg_dish(), profile) is True


def test_vegetarian_never_allows_a_meat_dish() -> None:
    profile = _profile(diet_type="vegetarian", egg_frequency=None)
    assert diet_type_allows(_meat_dish("chicken"), profile) is False


def test_vegetarian_never_allows_an_egg_dish() -> None:
    # Hard gate, not emergent from quota math — a Vegetarian must never get an egg dish even if
    # some other computation's target dates were wrong.
    profile = _profile(diet_type="vegetarian", egg_frequency=None)
    assert diet_type_allows(_egg_dish(), profile) is False


def test_eggetarian_never_allows_a_real_meat_dish() -> None:
    profile = _profile(diet_type="eggetarian", egg_frequency="any")
    assert diet_type_allows(_meat_dish("chicken"), profile) is False


def test_eggetarian_allows_an_egg_dish_when_frequency_is_not_never() -> None:
    for egg_frequency in ("any", "nonveg_days", "specific"):
        profile = _profile(diet_type="eggetarian", egg_frequency=egg_frequency)
        assert diet_type_allows(_egg_dish(), profile) is True


def test_eggetarian_never_allows_an_egg_dish_when_frequency_is_never() -> None:
    profile = _profile(diet_type="eggetarian", egg_frequency="never")
    assert diet_type_allows(_egg_dish(), profile) is False


def test_nonvegetarian_with_no_meat_types_restriction_allows_any_meat_type() -> None:
    profile = _profile(diet_type="nonvegetarian", egg_frequency="any", nonveg_days_per_week=1)
    for meat_type in ("chicken", "mutton", "fish", "seafood", "other"):
        assert diet_type_allows(_meat_dish(meat_type), profile) is True


def test_nonvegetarian_with_a_meat_types_restriction_rejects_other_meat_types() -> None:
    profile = _profile(
        diet_type="nonvegetarian",
        meat_types=["chicken"],
        egg_frequency="any",
        nonveg_days_per_week=1,
    )
    assert diet_type_allows(_meat_dish("chicken"), profile) is True
    assert diet_type_allows(_meat_dish("mutton"), profile) is False


def test_a_restricted_meat_types_preference_fails_closed_on_an_unclassified_meat_dish() -> None:
    # meat_type=None is the "genuinely ambiguous mixed meat" case (0016's own migration comment) —
    # once the user has actually restricted meat_types, an unclassified dish must never be silently
    # guessed into eligibility. Matches normalized_dietary_flags' existing fail-closed precedent.
    profile = _profile(
        diet_type="nonvegetarian",
        meat_types=["chicken"],
        egg_frequency="any",
        nonveg_days_per_week=1,
    )
    assert diet_type_allows(_meat_dish(None), profile) is False


def test_an_unclassified_meat_dish_is_allowed_when_meat_types_is_unrestricted() -> None:
    profile = _profile(diet_type="nonvegetarian", egg_frequency="any", nonveg_days_per_week=1)
    assert diet_type_allows(_meat_dish(None), profile) is True


def test_is_egg_dish_requires_both_nonveg_and_the_egg_flag() -> None:
    assert is_egg_dish(_egg_dish()) is True
    assert is_egg_dish(_meat_dish("chicken")) is False
    assert is_egg_dish(_veg_dish()) is False
