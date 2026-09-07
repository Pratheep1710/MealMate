"""User profile and favorites tables (0002_user_profile_favorites_schema.sql)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, field_validator, model_validator

from app.models.day_names import normalize_day_name
from app.models.dish import DIETARY_FLAG_VALUES, MEAT_TYPE_VALUES

# Phase 8 (MP-024 Q1/Q4): matches user_profiles_diet_type_valid / user_profiles_egg_frequency_valid
# (supabase/migrations/0021_onboarding_diet_taxonomy.sql) exactly — same "one place both import it
# from" convention as DIETARY_FLAG_VALUES.
DIET_TYPE_VALUES = ("vegetarian", "eggetarian", "nonvegetarian")
EGG_FREQUENCY_VALUES = ("any", "nonveg_days", "specific", "never")


class UserProfile(BaseModel):
    id: uuid.UUID
    nonveg_days_per_week: int | None
    nonveg_day_pattern: list[str] | None
    dietary_restrictions: list[str]
    dinner_style: str
    planning_mode: str
    grocery_day: str
    timezone: str
    diet_type: str
    meat_types: list[str]
    egg_frequency: str | None
    egg_day_pattern: list[str]
    allergy_other_text: str | None

    @field_validator("dietary_restrictions")
    @classmethod
    def _restrictions_are_in_the_controlled_vocabulary(cls, value: list[str]) -> list[str]:
        # Must match dishes.dietary_flags' vocabulary exactly (DIETARY_FLAG_VALUES) — array-overlap
        # hard exclusion (catalog_repo.get_candidates) is case-sensitive, so a profile value that
        # drifts from this (e.g. "nuts" instead of "Nuts") would silently never exclude a matching
        # dish. Enforced again at the DB level by user_profiles_dietary_restrictions_valid (0017)
        # for writes that don't pass through this model.
        invalid = [v for v in value if v not in DIETARY_FLAG_VALUES]
        if invalid:
            raise ValueError(
                f"dietary_restrictions contains values outside the controlled vocabulary: {invalid}"
            )
        return value

    @field_validator("diet_type")
    @classmethod
    def _diet_type_is_in_the_controlled_vocabulary(cls, value: str) -> str:
        if value not in DIET_TYPE_VALUES:
            raise ValueError(f"diet_type {value!r} is outside the controlled vocabulary")
        return value

    @field_validator("meat_types")
    @classmethod
    def _meat_types_are_in_the_controlled_vocabulary(cls, value: list[str]) -> list[str]:
        invalid = [v for v in value if v not in MEAT_TYPE_VALUES]
        if invalid:
            raise ValueError(
                f"meat_types contains values outside the controlled vocabulary: {invalid}"
            )
        return value

    @field_validator("egg_frequency")
    @classmethod
    def _egg_frequency_is_in_the_controlled_vocabulary(cls, value: str | None) -> str | None:
        if value is not None and value not in EGG_FREQUENCY_VALUES:
            raise ValueError(f"egg_frequency {value!r} is outside the controlled vocabulary")
        return value

    @model_validator(mode="after")
    def _nonveg_count_matches_pattern(self) -> UserProfile:
        """The frozen technical contract requires nonveg_days_per_week to equal the pattern's
        distinct day count whenever a pattern is set — otherwise a WeeklyContext built from this
        profile would expose a required-day count that contradicts its own weekly quota, which no
        downstream generator or validator could satisfy. Both fields are client-updatable with no
        DB constraint, so this model — the boundary every read and write already passes through
        (app/repositories/profiles.py) — is where the invariant has to be held.
        """
        if not self.nonveg_day_pattern:
            return self
        distinct_days = {normalize_day_name(day) for day in self.nonveg_day_pattern}
        if self.nonveg_days_per_week != len(distinct_days):
            raise ValueError(
                f"nonveg_days_per_week ({self.nonveg_days_per_week!r}) must equal the number of "
                f"distinct days in nonveg_day_pattern ({len(distinct_days)})"
            )
        return self

    @model_validator(mode="after")
    def _diet_taxonomy_fields_are_mutually_consistent(self) -> UserProfile:
        """Phase 8: mirrors supabase/migrations/0021_onboarding_diet_taxonomy.sql's CHECK
        constraints in this model too — the same defense-in-depth reasoning as
        _nonveg_count_matches_pattern above, since a direct client write bypasses this model
        entirely and only the DB constraints would catch it there.
        """
        if self.diet_type != "nonvegetarian" and self.meat_types:
            raise ValueError("meat_types must be empty unless diet_type is nonvegetarian")
        if self.diet_type == "vegetarian" and self.egg_frequency is not None:
            raise ValueError("egg_frequency must be null when diet_type is vegetarian")
        if self.diet_type != "vegetarian" and self.egg_frequency is None:
            raise ValueError("egg_frequency is required unless diet_type is vegetarian")
        if self.egg_frequency != "specific" and self.egg_day_pattern:
            raise ValueError("egg_day_pattern must be empty unless egg_frequency is 'specific'")
        if self.diet_type != "nonvegetarian" and self.nonveg_days_per_week:
            raise ValueError("nonveg_days_per_week must be unset unless diet_type is nonvegetarian")
        if self.diet_type != "nonvegetarian" and self.nonveg_day_pattern:
            raise ValueError("nonveg_day_pattern must be empty unless diet_type is nonvegetarian")
        return self


class UserFavoriteDish(BaseModel):
    user_id: uuid.UUID
    dish_id: uuid.UUID
