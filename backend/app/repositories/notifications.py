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
    "created_at, updated_at, delivered_at"
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


def try_claim(
    conn: psycopg.Connection[DictRow], notification_id: uuid.UUID
) -> NotificationLog | None:
    """MP-070 review fix: atomically transitions a notification_log row to 'processing' so two
    overlapping runs can't both send the same reminder (see 0015's migration comment). Returns
    the updated row if this call won the transition, or None if it was already sent/delivered,
    already claimed by a concurrent run, or has used up should_send_reminder's one-retry budget
    (mirrored here in SQL rather than in a separate read-then-write step, which is exactly the
    race this closes) — callers must only send when this returns non-None.
    """
    row = conn.execute(
        f"""
        update notification_log
        set status = 'processing', updated_at = now()
        where id = %s
          and (status = 'pending' or (status = 'failed' and attempt < 2))
        returning {_COLUMNS}
        """,
        (notification_id,),
    ).fetchone()
    return NotificationLog.model_validate(row) if row else None


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
            updated_at = now(),
            delivered_at = case when %s = 'delivered' then now() else delivered_at end
        where id = %s
        returning {_COLUMNS}
        """,
        (status, expo_ticket_id, 1 if increment_attempt else 0, status, notification_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"notification_log row {notification_id} not found")
    return NotificationLog.model_validate(row)


def list_sent_awaiting_reconciliation(
    conn: psycopg.Connection[DictRow], *, before: datetime.datetime
) -> list[NotificationLog]:
    """MP-073: rows a ticket was issued for but whose actual delivery outcome (Expo's receipt) has
    never been checked. `before` is the reconciliation job's own "now minus a buffer" — Expo's
    receipts aren't necessarily available the instant a ticket is issued, and `updated_at` is set
    the moment the row was marked 'sent', so this only picks up rows old enough that a receipt is
    actually likely to exist yet (the ~30-minute-later follow-up from the technical spec's outbox
    diagram). A row missing `expo_ticket_id` was never actually sent (the "failed" branch never
    gets one) and has nothing to reconcile against.
    """
    rows = conn.execute(
        f"""
        select {_COLUMNS} from notification_log
        where status = 'sent' and expo_ticket_id is not null and updated_at < %s
        """,
        (before,),
    ).fetchall()
    return [NotificationLog.model_validate(row) for row in rows]


def list_for_target_date(
    conn: psycopg.Connection[DictRow], notification_type: str, target_date: datetime.date
) -> list[NotificationLog]:
    rows = conn.execute(
        f"select {_COLUMNS} from notification_log "
        "where notification_type = %s and target_date = %s",
        (notification_type, target_date),
    ).fetchall()
    return [NotificationLog.model_validate(row) for row in rows]
