"""MP-031: plan history queries for the 10-day no-repeat rule (docs/MP-001, "In scope for v1" —
applies against history and within the generated week; `track_variety = false` dishes are exempt
globally).
"""

from __future__ import annotations

import datetime
import uuid

import psycopg
from psycopg.rows import DictRow


def get_recent_variety_dish_ids(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    since: datetime.date,
    before: datetime.date,
) -> list[uuid.UUID]:
    """Dish ids the user was served in `[since, before)` — `since` inclusive, `before` exclusive —
    restricted to `track_variety = true` dishes. The exclusive upper bound matters: without it,
    today's (or a future generated week's) already-assigned dishes would count as "recent history"
    and wrongly exclude themselves from their own candidate pool.

    Excludes skipped/eating-out days (`meal_plans.is_skipped`, migration 0007): functional spec §6
    requires a skipped slot to drop out of variety/history tracking entirely, since the dish was
    never actually eaten.
    """
    rows = conn.execute(
        """
        select distinct pi.dish_id
        from plan_items pi
        join meal_plans mp on mp.id = pi.plan_id
        join dishes d on d.id = pi.dish_id
        where mp.user_id = %s
          and mp.plan_date >= %s
          and mp.plan_date < %s
          and d.track_variety = true
          and mp.is_skipped = false
        """,
        (user_id, since, before),
    ).fetchall()
    return [row["dish_id"] for row in rows]


def get_dish_last_used_dates(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    before: datetime.date,
) -> dict[uuid.UUID, datetime.date]:
    """Last non-skipped use before ``before`` for deterministic fallback ranking."""
    rows = conn.execute(
        """
        select pi.dish_id, max(mp.plan_date) as last_used
        from plan_items pi
        join meal_plans mp on mp.id = pi.plan_id
        where mp.user_id = %s
          and mp.plan_date < %s
          and mp.is_skipped = false
          and pi.status = 'filled'
          and pi.dish_id is not null
        group by pi.dish_id
        """,
        (user_id, before),
    ).fetchall()
    return {row["dish_id"]: row["last_used"] for row in rows}


def get_nonveg_plan_dates(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    since: datetime.date,
    before: datetime.date,
) -> set[datetime.date]:
    """Dates in ``[since, before)`` whose live plan contains at least one non-veg dish."""
    rows = conn.execute(
        """
        select distinct mp.plan_date
        from meal_plans mp
        join plan_items pi on pi.plan_id = mp.id
        join dishes d on d.id = pi.dish_id
        where mp.user_id = %s
          and mp.plan_date >= %s
          and mp.plan_date < %s
          and mp.is_skipped = false
          and pi.status = 'filled'
          and d.veg_or_nonveg = 'nonveg'
        """,
        (user_id, since, before),
    ).fetchall()
    return {row["plan_date"] for row in rows}
