"""UserProfile's nonveg_days_per_week / nonveg_day_pattern cross-field validation
(app/models/profile.py) — pure model tests, no DB needed.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models import UserProfile


def _profile(
    *,
    nonveg_days_per_week: int | None,
    nonveg_day_pattern: list[str] | None,
    diet_type: str = "nonvegetarian",
    meat_types: list[str] | None = None,
    egg_frequency: str | None = "any",
    egg_day_pattern: list[str] | None = None,
) -> UserProfile:
    return UserProfile(
        id=uuid.uuid4(),
        nonveg_days_per_week=nonveg_days_per_week,
        nonveg_day_pattern=nonveg_day_pattern,
        dietary_restrictions=[],
        dinner_style="rice",
        planning_mode="suggestion",
        grocery_day="monday",
        timezone="Asia/Kolkata",
        diet_type=diet_type,
        meat_types=meat_types or [],
        egg_frequency=egg_frequency,
        egg_day_pattern=egg_day_pattern or [],
        allergy_other_text=None,
    )


def test_a_pattern_whose_length_matches_the_count_validates() -> None:
    profile = _profile(nonveg_days_per_week=2, nonveg_day_pattern=["wed", "sat"])
    assert profile.nonveg_days_per_week == 2


def test_a_pattern_shorter_than_the_stated_count_is_rejected() -> None:
    with pytest.raises(ValidationError, match="nonveg_days_per_week"):
        _profile(nonveg_days_per_week=5, nonveg_day_pattern=["wed"])


def test_a_pattern_longer_than_the_stated_count_is_rejected() -> None:
    with pytest.raises(ValidationError, match="nonveg_days_per_week"):
        _profile(nonveg_days_per_week=1, nonveg_day_pattern=["wed", "sat", "sun"])


def test_duplicate_days_count_once_toward_the_required_match() -> None:
    # ["wed", "wed"] is one distinct day, not two — a count of 2 must still be rejected.
    with pytest.raises(ValidationError, match="nonveg_days_per_week"):
        _profile(nonveg_days_per_week=2, nonveg_day_pattern=["wed", "wed"])


def test_the_abbreviated_and_full_forms_of_the_same_day_are_recognized_as_one() -> None:
    with pytest.raises(ValidationError, match="nonveg_days_per_week"):
        _profile(nonveg_days_per_week=2, nonveg_day_pattern=["wed", "wednesday"])


def test_a_count_set_without_any_pattern_needs_no_match() -> None:
    # No pattern means the count is a flexible, generation-time constraint (see
    # weekly_context.py) rather than a per-day pin — nothing to cross-check yet.
    profile = _profile(nonveg_days_per_week=3, nonveg_day_pattern=None)
    assert profile.nonveg_day_pattern is None


def test_an_empty_pattern_needs_no_match() -> None:
    profile = _profile(nonveg_days_per_week=3, nonveg_day_pattern=[])
    assert profile.nonveg_day_pattern == []


# Phase 8 (MP-024): diet_type/meat_types/egg_frequency/egg_day_pattern coupling — mirrors
# supabase/migrations/0021_onboarding_diet_taxonomy.sql's CHECK constraints in this model too,
# same defense-in-depth reasoning as the nonveg_days_per_week/pattern tests above.


def test_meat_types_requires_nonvegetarian_diet_type() -> None:
    with pytest.raises(ValidationError, match="meat_types"):
        _profile(
            nonveg_days_per_week=None,
            nonveg_day_pattern=None,
            diet_type="eggetarian",
            meat_types=["chicken"],
            egg_frequency="any",
        )


def test_vegetarian_requires_no_egg_frequency() -> None:
    with pytest.raises(ValidationError, match="egg_frequency"):
        _profile(
            nonveg_days_per_week=None,
            nonveg_day_pattern=None,
            diet_type="vegetarian",
            egg_frequency="any",
        )


def test_vegetarian_with_no_egg_frequency_validates() -> None:
    profile = _profile(
        nonveg_days_per_week=None,
        nonveg_day_pattern=None,
        diet_type="vegetarian",
        egg_frequency=None,
    )
    assert profile.diet_type == "vegetarian"


def test_eggetarian_requires_an_egg_frequency() -> None:
    with pytest.raises(ValidationError, match="egg_frequency"):
        _profile(
            nonveg_days_per_week=None,
            nonveg_day_pattern=None,
            diet_type="eggetarian",
            egg_frequency=None,
        )


def test_egg_day_pattern_requires_specific_frequency() -> None:
    with pytest.raises(ValidationError, match="egg_day_pattern"):
        _profile(
            nonveg_days_per_week=None,
            nonveg_day_pattern=None,
            diet_type="eggetarian",
            egg_frequency="any",
            egg_day_pattern=["wed"],
        )


def test_egg_day_pattern_with_specific_frequency_validates() -> None:
    profile = _profile(
        nonveg_days_per_week=None,
        nonveg_day_pattern=None,
        diet_type="eggetarian",
        egg_frequency="specific",
        egg_day_pattern=["wed"],
    )
    assert profile.egg_day_pattern == ["wed"]


def test_nonveg_days_per_week_requires_nonvegetarian_diet_type() -> None:
    with pytest.raises(ValidationError, match="nonveg_days_per_week"):
        _profile(
            nonveg_days_per_week=2,
            nonveg_day_pattern=None,
            diet_type="eggetarian",
            egg_frequency="any",
        )


def test_nonveg_day_pattern_requires_nonvegetarian_diet_type() -> None:
    with pytest.raises(ValidationError, match="nonveg_day_pattern"):
        _profile(
            nonveg_days_per_week=None,
            nonveg_day_pattern=["wed"],
            diet_type="vegetarian",
            egg_frequency=None,
        )


def test_an_unknown_diet_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="diet_type"):
        _profile(nonveg_days_per_week=None, nonveg_day_pattern=None, diet_type="pescatarian")


def test_an_unknown_meat_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="meat_types"):
        _profile(
            nonveg_days_per_week=1,
            nonveg_day_pattern=None,
            diet_type="nonvegetarian",
            meat_types=["beef"],
            egg_frequency="any",
        )


def test_an_unknown_egg_frequency_is_rejected() -> None:
    with pytest.raises(ValidationError, match="egg_frequency"):
        _profile(
            nonveg_days_per_week=None,
            nonveg_day_pattern=None,
            diet_type="eggetarian",
            egg_frequency="weekly",
        )
