"""Internal Phase 6 result types shared by the LLM and fallback paths."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Literal

from app.schemas.weekly_menu import WeeklyMenu

PlanItemStatus = Literal["filled", "needs_manual_pick"]
GenerationSource = Literal["openai", "fallback"]


@dataclass(frozen=True)
class PlannedItem:
    day: datetime.date
    slot: str
    item_type: str
    dish_id: uuid.UUID | None
    status: PlanItemStatus = "filled"


@dataclass(frozen=True)
class GeneratedPlan:
    week_start: datetime.date
    items: tuple[PlannedItem, ...]
    source: GenerationSource


def plan_from_menu(menu: WeeklyMenu) -> GeneratedPlan:
    return GeneratedPlan(
        week_start=menu.week_start,
        items=tuple(
            PlannedItem(
                day=item.day,
                slot=item.slot,
                item_type=item.item_type,
                dish_id=item.dish_id,
            )
            for item in menu.items
        ),
        source="openai",
    )
