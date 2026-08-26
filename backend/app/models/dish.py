"""Catalog tables (0001_dish_ingredient_schema.sql) — read-only at the app layer; written only
by the MP-018 ingestion job.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, field_validator

# MP-017's decided controlled vocabulary (Phase 5 brief §0) — matches the app's onboarding allergy
# question exactly, casing included, so the same values work on both sides of the hard-exclusion
# array-overlap check with no translation layer. Enforced at the DB level too
# (dishes_dietary_flags_valid, 0016) and on UserProfile.dietary_restrictions (app/models/profile.py,
# user_profiles_dietary_restrictions_valid, 0017) — this is the one place both import it from, so
# a future vocabulary change can't update one side and silently miss the other. The
# scripting-side copy in supabase/seed/catalog_taxonomy.py can't import from here (it's a
# standalone script directory outside the `app` package, run as one-off admin tooling rather than
# through the backend service) and has to be kept in sync by hand — see that module's own comment.
DIETARY_FLAG_VALUES = ("Nuts", "Milk-Dairy", "Gluten", "Egg", "Seafood", "Sesame")


class Dish(BaseModel):
    id: uuid.UUID
    name: str
    item_type: str
    veg_or_nonveg: str
    region_style: str | None
    prep_minutes: int | None
    track_variety: bool
    dietary_flags: list[str]

    @field_validator("dietary_flags")
    @classmethod
    def _flags_are_in_the_controlled_vocabulary(cls, value: list[str]) -> list[str]:
        invalid = [v for v in value if v not in DIETARY_FLAG_VALUES]
        if invalid:
            raise ValueError(f"dietary_flags has values outside the vocabulary: {invalid}")
        return value


class Ingredient(BaseModel):
    id: uuid.UUID
    canonical_name: str
    is_staple: bool


class IngredientAlias(BaseModel):
    alias_text: str
    ingredient_id: uuid.UUID


class DishIngredient(BaseModel):
    dish_id: uuid.UUID
    ingredient_id: uuid.UUID
