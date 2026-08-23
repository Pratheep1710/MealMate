"""MP-031: notification_log — feeds MP-005's SLO measurement (app/services/notification_slo.py)
and the outbox-pattern ticket/receipt reconciliation (docs/MP-001 "Core").
"""

from __future__ import annotations

import datetime
import uuid

import psycopg
from psycopg.rows import DictRow

from app.models import NotificationLog

_COLUMNS = (
    "id, user_id, notification_type, target_date, status, expo_ticket_id, attempt, "
    "created_at, updated_at"
)


def upsert_pending(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    notification_type: str,
    target_date: datetime.date,
) -> NotificationLog:
    row = conn.execute(
        f"""
        insert into notification_log (user_id, notification_type, target_date)
        values (%s, %s, %s)
        on conflict (user_id, notification_type, target_date) do update set
            user_id = excluded.user_id
        returning {_COLUMNS}
        """,
        (user_id, notification_type, target_date),
    ).fetchone()
    assert row is not None
    return NotificationLog.model_validate(row)


def mark_status(
    conn: psycopg.Connection[DictRow],
    notification_id: uuid.UUID,
    status: str,
    *,
    expo_ticket_id: str | None = None,
    increment_attempt: bool = False,
) -> NotificationLog:
    row = conn.execute(
        f"""
        update notification_log
        set status = %s,
            expo_ticket_id = coalesce(%s, expo_ticket_id),
            attempt = attempt + %s,
            updated_at = now()
        where id = %s
        returning {_COLUMNS}
        """,
        (status, expo_ticket_id, 1 if increment_attempt else 0, notification_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"notification_log row {notification_id} not found")
    return NotificationLog.model_validate(row)


def list_for_target_date(
    conn: psycopg.Connection[DictRow], notification_type: str, target_date: datetime.date
) -> list[NotificationLog]:
    rows = conn.execute(
        f"select {_COLUMNS} from notification_log "
        "where notification_type = %s and target_date = %s",
        (notification_type, target_date),
    ).fetchall()
    return [NotificationLog.model_validate(row) for row in rows]
