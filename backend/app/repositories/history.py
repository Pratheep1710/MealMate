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
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, since: datetime.date
) -> list[uuid.UUID]:
    """Dish ids the user was served on or after `since`, restricted to `track_variety = true`
    dishes — the exact set the 10-day rule needs to exclude from the next candidate pool.
    """
    rows = conn.execute(
        """
        select distinct pi.dish_id
        from plan_items pi
        join meal_plans mp on mp.id = pi.plan_id
        join dishes d on d.id = pi.dish_id
        where mp.user_id = %s and mp.plan_date >= %s and d.track_variety = true
        """,
        (user_id, since),
    ).fetchall()
    return [row["dish_id"] for row in rows]
