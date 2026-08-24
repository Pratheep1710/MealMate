"""Catalog tables (0001_dish_ingredient_schema.sql) — read-only at the app layer; written only
by the MP-018 ingestion job.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class Dish(BaseModel):
    id: uuid.UUID
    name: str
    item_type: str
    veg_or_nonveg: str
    region_style: str | None
    prep_minutes: int | None
    track_variety: bool
    dietary_flags: list[str]


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
