"""MP-031: user_profiles + user_favorite_dishes."""

from __future__ import annotations

import uuid

import psycopg
from psycopg.rows import DictRow

from app.models import UserProfile

_COLUMNS = (
    "id, nonveg_days_per_week, nonveg_day_pattern, dietary_restrictions, "
    "dinner_style, planning_mode, grocery_day, timezone"
)


def get_profile(conn: psycopg.Connection[DictRow], user_id: uuid.UUID) -> UserProfile | None:
    row = conn.execute(
        f"select {_COLUMNS} from user_profiles where id = %s", (user_id,)
    ).fetchone()
    return UserProfile.model_validate(row) if row else None


def upsert_profile(conn: psycopg.Connection[DictRow], profile: UserProfile) -> UserProfile:
    row = conn.execute(
        f"""
        insert into user_profiles
            (id, nonveg_days_per_week, nonveg_day_pattern, dietary_restrictions,
             dinner_style, planning_mode, grocery_day, timezone)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (id) do update set
            nonveg_days_per_week = excluded.nonveg_days_per_week,
            nonveg_day_pattern = excluded.nonveg_day_pattern,
            dietary_restrictions = excluded.dietary_restrictions,
            dinner_style = excluded.dinner_style,
            planning_mode = excluded.planning_mode,
            grocery_day = excluded.grocery_day,
            timezone = excluded.timezone
        returning {_COLUMNS}
        """,
        (
            profile.id,
            profile.nonveg_days_per_week,
            profile.nonveg_day_pattern,
            profile.dietary_restrictions,
            profile.dinner_style,
            profile.planning_mode,
            profile.grocery_day,
            profile.timezone,
        ),
    ).fetchone()
    assert row is not None
    return UserProfile.model_validate(row)


def list_favorite_dish_ids(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID
) -> list[uuid.UUID]:
    rows = conn.execute(
        "select dish_id from user_favorite_dishes where user_id = %s", (user_id,)
    ).fetchall()
    return [row["dish_id"] for row in rows]


def add_favorite(conn: psycopg.Connection[DictRow], user_id: uuid.UUID, dish_id: uuid.UUID) -> None:
    conn.execute(
        "insert into user_favorite_dishes (user_id, dish_id) values (%s, %s) "
        "on conflict do nothing",
        (user_id, dish_id),
    )


def remove_favorite(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, dish_id: uuid.UUID
) -> None:
    conn.execute(
        "delete from user_favorite_dishes where user_id = %s and dish_id = %s",
        (user_id, dish_id),
    )
