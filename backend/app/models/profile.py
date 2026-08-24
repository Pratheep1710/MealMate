"""User profile and favorites tables (0002_user_profile_favorites_schema.sql)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class UserProfile(BaseModel):
    id: uuid.UUID
    nonveg_days_per_week: int | None
    nonveg_day_pattern: list[str] | None
    dietary_restrictions: list[str]
    dinner_style: str
    planning_mode: str
    grocery_day: str
    timezone: str


class UserFavoriteDish(BaseModel):
    user_id: uuid.UUID
    dish_id: uuid.UUID
