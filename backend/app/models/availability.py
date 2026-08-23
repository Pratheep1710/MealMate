"""Availability and grocery snapshot tables (0005_availability_grocery_snapshot_schema.sql)."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel


class AvailableIngredient(BaseModel):
    user_id: uuid.UUID
    week_start: datetime.date
    ingredient_id: uuid.UUID


class GroceryListSnapshot(BaseModel):
    user_id: uuid.UUID
    week_start: datetime.date
    ingredients: list[dict[str, Any]]
    created_at: datetime.datetime
