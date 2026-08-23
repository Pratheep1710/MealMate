"""Meal plan tables (0003_meal_plan_schema.sql)."""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel


class MealPlan(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    plan_date: datetime.date
    slot: str
    created_at: datetime.datetime


class PlanItem(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    item_type: str
    dish_id: uuid.UUID | None
    make_extra: bool
    status: str
