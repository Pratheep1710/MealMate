"""MP-031: available_ingredients — Reserves-mode manual availability checklist."""

from __future__ import annotations

import datetime
import uuid

import psycopg
from psycopg.rows import DictRow


def get_available_ingredient_ids(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, week_start: datetime.date
) -> list[uuid.UUID]:
    rows = conn.execute(
        "select ingredient_id from available_ingredients where user_id = %s and week_start = %s",
        (user_id, week_start),
    ).fetchall()
    return [row["ingredient_id"] for row in rows]


def set_available_ingredients(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    week_start: datetime.date,
    ingredient_ids: list[uuid.UUID],
) -> None:
    """Replaces the full set for (user_id, week_start) — matches the mobile checklist's
    save-the-whole-list interaction (v1 manual checklist, per docs/MP-001) rather than
    incremental per-item toggles.
    """
    conn.execute(
        "delete from available_ingredients where user_id = %s and week_start = %s",
        (user_id, week_start),
    )
    if ingredient_ids:
        with conn.cursor() as cur:
            cur.executemany(
                "insert into available_ingredients (user_id, week_start, ingredient_id) "
                "values (%s, %s, %s)",
                [(user_id, week_start, ingredient_id) for ingredient_id in ingredient_ids],
            )
