"""User profile and favorites tables (0002_user_profile_favorites_schema.sql)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, model_validator

from app.models.day_names import normalize_day_name


class UserProfile(BaseModel):
    id: uuid.UUID
    nonveg_days_per_week: int | None
    nonveg_day_pattern: list[str] | None
    dietary_restrictions: list[str]
    dinner_style: str
    planning_mode: str
    grocery_day: str
    timezone: str

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


class UserFavoriteDish(BaseModel):
    user_id: uuid.UUID
    dish_id: uuid.UUID
