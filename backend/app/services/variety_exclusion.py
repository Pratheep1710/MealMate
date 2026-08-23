"""MP-035: rolling 10-day exclusion set for track_variety dishes (docs/MP-001, "no dish repeat
within a rolling 10-day window, scoped per track_variety dish... favorites exempt from the 10-day
rule only, per user"). Combines MP-031's raw history query with the user's favorite dish ids so a
favorite never gets excluded here, even though it's a track_variety dish served recently.
"""

from __future__ import annotations

import datetime
import uuid

import psycopg
from psycopg.rows import DictRow

from app.repositories import history as history_repo
from app.repositories import profiles as profiles_repo

_WINDOW_DAYS = 10


def get_variety_exclusion_set(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, as_of: datetime.date
) -> set[uuid.UUID]:
    """Dish ids to exclude from `as_of`'s candidate pool: track_variety dishes served in the prior
    ten days [as_of - 10, as_of - 1] (exactly ten days ago is still excluded; eleven is not),
    minus the user's favorites.
    """
    since = as_of - datetime.timedelta(days=_WINDOW_DAYS)
    recent = history_repo.get_recent_variety_dish_ids(conn, user_id, since)
    favorites = set(profiles_repo.list_favorite_dish_ids(conn, user_id))
    return set(recent) - favorites
