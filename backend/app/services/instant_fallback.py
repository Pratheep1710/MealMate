"""Phase 9 (MP-093): instant, zero-LLM fallback meals for a screen rendered right after
onboarding, before real generation has completed. Deliberately not a new implementation of any
filtering/eligibility logic — this is a thin wrapper around the exact machinery generation
already uses: build_generation_context (Phase 6) + build_fallback_plan (the shared,
diet_type_allows/is_eligible-enforced deterministic path also used inside run_generation_engine
whenever the LLM path fails). No job claim, no persistence, no LLM call — purely computed and
handed back for the caller to render.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

import psycopg
from psycopg.rows import DictRow

from app.models import Dish
from app.services.generation_context import build_generation_context
from app.services.generation_models import PlannedItem
from app.services.planning_trigger import week_start_monday
from app.services.rule_based_fallback import build_fallback_plan


@dataclass(frozen=True)
class InstantFallback:
    items: tuple[PlannedItem, ...]
    dishes_by_id: Mapping[uuid.UUID, Dish]


def build_instant_fallback(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    today: datetime.date,
    *,
    days_ahead: int = 2,
) -> InstantFallback:
    """Items for `today` through `today + days_ahead - 1` only — MP-092 renders 1-2 slots, not a
    full week, so there is no reason to hand back more than a couple of days' worth of picks.
    """
    context = build_generation_context(
        conn, user_id, week_start_monday(today), start_date=today
    )
    plan = build_fallback_plan(context)
    cutoff = today + datetime.timedelta(days=days_ahead - 1)
    items = tuple(item for item in plan.items if item.day <= cutoff)
    return InstantFallback(items=items, dishes_by_id=context.dishes_by_id)
