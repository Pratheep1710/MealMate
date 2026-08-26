"""Initial Phase 6 generation context assembly (MP-034/038/039 foundation).

The model-facing catalogue is intentionally filtered by slot item type only. It is *not* narrowed
by a user's restrictions or recent history: the technical contract keeps that catalogue as a
shared, cache-friendly prefix and supplies user-specific exclusions in the dynamic suffix. The
response validator and rule-based fallback remain responsible for enforcing those hard rules.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

import psycopg
from psycopg.rows import DictRow

from app.models import Dish, UserProfile
from app.repositories import availability as availability_repo
from app.repositories import catalog as catalog_repo
from app.repositories import profiles as profiles_repo
from app.services.slot_templates import GENERATION_ITEM_TYPES, SlotTemplate, templates_for_profile
from app.services.variety_exclusion import get_variety_exclusion_set
from app.services.weekly_context import DayContext, WeeklyContext, compute_weekly_context

_WEEK_LENGTH_DAYS = 7


@dataclass(frozen=True)
class CatalogGroup:
    item_type: str
    dishes: tuple[Dish, ...]


@dataclass(frozen=True)
class GenerationContext:
    profile: UserProfile
    week: WeeklyContext
    target_days: tuple[DayContext, ...]
    slot_templates: tuple[SlotTemplate, ...]
    catalog: tuple[CatalogGroup, ...]
    recent_dish_ids: frozenset[uuid.UUID]
    available_ingredient_ids: frozenset[uuid.UUID]

    @property
    def target_dates(self) -> tuple[datetime.date, ...]:
        return tuple(day.date for day in self.target_days)

    @property
    def candidate_dish_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(dish.id for group in self.catalog for dish in group.dishes)


def build_generation_context(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    week_start: datetime.date,
    *,
    start_date: datetime.date | None = None,
) -> GenerationContext:
    """Assemble the static catalogue prefix and dynamic per-user suffix for one generation run.

    ``start_date`` supports the existing regenerate-remaining-week contract. It must be inside the
    target week; history is evaluated immediately before that date, and only that date onward is
    included in ``target_days``.
    """
    effective_start = start_date or week_start
    week_end = week_start + datetime.timedelta(days=_WEEK_LENGTH_DAYS - 1)
    if not week_start <= effective_start <= week_end:
        raise ValueError(
            f"start_date {effective_start.isoformat()} is outside week "
            f"{week_start.isoformat()}..{week_end.isoformat()}"
        )

    profile = profiles_repo.get_profile(conn, user_id)
    if profile is None:
        raise ValueError(f"user profile {user_id} not found")
    if profile.planning_mode not in ("suggestion", "reserves"):
        raise ValueError(f"unsupported planning_mode: {profile.planning_mode!r}")

    week = compute_weekly_context(profile, week_start)
    target_days = tuple(day for day in week.days if day.date >= effective_start)

    # Do not add per-user filters here. Keeping this prefix stable is an explicit prompt-caching
    # requirement; dietary/history rules travel separately and are validated after the model call.
    catalog = tuple(
        CatalogGroup(
            item_type,
            tuple(
                sorted(
                    catalog_repo.get_candidates(conn, item_type=item_type),
                    key=lambda dish: (dish.name.casefold(), str(dish.id)),
                )
            ),
        )
        for item_type in GENERATION_ITEM_TYPES
    )
    recent_dish_ids = frozenset(get_variety_exclusion_set(conn, user_id, effective_start))

    if profile.planning_mode == "reserves":
        available_ingredient_ids = frozenset(
            availability_repo.get_available_ingredient_ids(conn, user_id, week_start)
        )
    else:
        available_ingredient_ids = frozenset()

    return GenerationContext(
        profile=profile,
        week=week,
        target_days=target_days,
        slot_templates=templates_for_profile(profile),
        catalog=catalog,
        recent_dish_ids=recent_dish_ids,
        available_ingredient_ids=available_ingredient_ids,
    )
