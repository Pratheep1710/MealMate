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
