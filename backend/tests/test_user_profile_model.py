"""UserProfile's nonveg_days_per_week / nonveg_day_pattern cross-field validation
(app/models/profile.py) — pure model tests, no DB needed.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models import UserProfile


def _profile(
    *, nonveg_days_per_week: int | None, nonveg_day_pattern: list[str] | None
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
