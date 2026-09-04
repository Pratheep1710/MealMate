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

# MP-063: must match supabase/migrations/0018_favorites_cap.sql's `favorites_cap` constant — that
# trigger is the real enforcement (it holds regardless of insert path, including the mobile
# client's own direct RLS insert this backend connection never sees), this is a friendlier error
# for any backend-driven caller (tests, admin scripts) that would otherwise just see a raw
# Postgres check_violation.
FAVORITES_CAP = 8


class FavoritesCapExceeded(Exception):
    """Raised before the insert is attempted, mirroring the DB trigger's own limit."""


def get_profile(conn: psycopg.Connection[DictRow], user_id: uuid.UUID) -> UserProfile | None:
    row = conn.execute(
        f"select {_COLUMNS} from user_profiles where id = %s", (user_id,)
    ).fetchone()
    return UserProfile.model_validate(row) if row else None


def list_profiles(conn: psycopg.Connection[DictRow]) -> list[UserProfile]:
    """All profiles considered by the family-scale daily generation sweep."""
    rows = conn.execute(f"select {_COLUMNS} from user_profiles order by id").fetchall()
    return [UserProfile.model_validate(row) for row in rows]


def upsert_profile(conn: psycopg.Connection[DictRow], profile: UserProfile) -> UserProfile:
    """`planning_mode` is deliberately insert-only: it's set from `profile.planning_mode` on the
    first (onboarding) insert, but the `on conflict` branch omits it from the update list, so a
    later call with a different `planning_mode` is silently ignored rather than applied. Migration
    0009 enforces the same onboarding-only invariant at the DB layer, but only against the
    `authenticated` Postgres role's own column grant — this backend connection uses a more
    privileged role that grant doesn't restrict, so the invariant has to be enforced here too, not
    just at the RLS/grant layer (functional spec §2: planning_mode is immutable after onboarding).
    """
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
    """Re-adding an already-favorited dish is a no-op (`on conflict do nothing`) and never counts
    against the cap — only a genuinely new favorite can trip `FavoritesCapExceeded`.
    """
    existing = list_favorite_dish_ids(conn, user_id)
    if dish_id not in existing and len(existing) >= FAVORITES_CAP:
        raise FavoritesCapExceeded(
            f"user {user_id} already has {len(existing)} favorites (cap is {FAVORITES_CAP})"
        )
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
