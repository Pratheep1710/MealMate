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

# Phase 8 (MP-024 Q2): the meat-type preference question's vocabulary, matching dishes.meat_type's
# own DB constraint exactly (0016_dishes_meat_type_and_taxonomy_constraints.sql,
# dishes_meat_type_valid) — this is the one place both import it from, same convention as
# DIETARY_FLAG_VALUES above. Egg-diet dishes are identified separately, via
# dietary_flags @> {"Egg"} (see app/services/generation_eligibility.py's _is_egg_dish) — meat_type
# stays null for them, matching the ingestion pipeline's own convention
# (supabase/seed/catalog_taxonomy.py's infer_meat_type docstring).
MEAT_TYPE_VALUES = ("chicken", "mutton", "fish", "seafood", "other")


class Dish(BaseModel):
    id: uuid.UUID
    name: str
    item_type: str
    veg_or_nonveg: str
    region_style: str | None
    prep_minutes: int | None
    track_variety: bool
    dietary_flags: list[str]
    meat_type: str | None = None

    @field_validator("dietary_flags")
    @classmethod
    def _flags_are_in_the_controlled_vocabulary(cls, value: list[str]) -> list[str]:
        invalid = [v for v in value if v not in DIETARY_FLAG_VALUES]
        if invalid:
            raise ValueError(f"dietary_flags has values outside the vocabulary: {invalid}")
        return value

    @field_validator("meat_type")
    @classmethod
    def _meat_type_is_in_the_controlled_vocabulary(cls, value: str | None) -> str | None:
        if value is not None and value not in MEAT_TYPE_VALUES:
            raise ValueError(f"meat_type {value!r} is outside the controlled vocabulary")
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
