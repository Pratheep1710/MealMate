"""MP-068: push_tokens — read path for MP-070's send job. Registration itself is a direct
RLS-scoped client write (mobile/src/lib/pushRegistration.ts), not a backend repository call.
"""

from __future__ import annotations

import uuid

import psycopg
from psycopg.rows import DictRow

from app.models import PushToken

_COLUMNS = "id, user_id, expo_push_token, created_at, updated_at"


def list_tokens_for_user(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID
) -> list[PushToken]:
    rows = conn.execute(
        f"select {_COLUMNS} from push_tokens where user_id = %s", (user_id,)
    ).fetchall()
    return [PushToken.model_validate(row) for row in rows]


def list_users_with_tokens(conn: psycopg.Connection[DictRow]) -> list[uuid.UUID]:
    """Distinct user ids with at least one registered device — MP-070's per-user fan-out list."""
    rows = conn.execute("select distinct user_id from push_tokens").fetchall()
    return [row["user_id"] for row in rows]
