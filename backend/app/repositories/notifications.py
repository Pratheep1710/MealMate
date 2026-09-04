"""MP-031: notification_log — feeds MP-005's SLO measurement (app/services/notification_slo.py)
and the outbox-pattern ticket/receipt reconciliation (docs/MP-001 "Core").
"""

from __future__ import annotations

import datetime
import uuid

import psycopg
from psycopg.rows import DictRow

from app.models import NotificationLog, NotificationLogDevice

_COLUMNS = (
    "id, user_id, notification_type, target_date, status, expo_ticket_id, attempt, "
    "created_at, updated_at, delivered_at"
)

_DEVICE_COLUMNS = (
    "id, notification_log_id, expo_push_token, status, expo_ticket_id, error, "
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


def try_claim(
    conn: psycopg.Connection[DictRow], notification_id: uuid.UUID
) -> NotificationLog | None:
    """MP-070 review fix: atomically transitions a notification_log row to 'processing' so two
    overlapping runs can't both send the same reminder (see 0015's migration comment). Returns
    the updated row if this call won the transition, or None if it was already sent/delivered,
    already claimed by a concurrent run, or already failed.

    PR review fix (Phase 7): this used to also reclaim a 'failed' row while attempt < 2, on the
    assumption that one claimed run makes exactly one real Expo attempt. That's no longer true —
    app/services/push_dispatch.send_expo_push_with_one_retry makes the initial attempt *and* the
    one same-evening retry inside a single claimed call (MP-072), so by the time a row is marked
    'failed' its whole retry budget is already spent. Reclaiming it here on top of that would let a
    later run spend the budget a second time (four real Expo attempts across two runs instead of
    two) — retry policy now lives in exactly one place: push_dispatch's own internal retry.
    """
    row = conn.execute(
        f"""
        update notification_log
        set status = 'processing', updated_at = now()
        where id = %s and status = 'pending'
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


def record_device_result(
    conn: psycopg.Connection[DictRow],
    notification_log_id: uuid.UUID,
    expo_push_token: str,
    status: str,
    *,
    expo_ticket_id: str | None = None,
    error: str | None = None,
) -> NotificationLogDevice:
    """MP-071 PR review fix: one audit row per push token a send was attempted for — a multi-device
    user's failed device no longer disappears just because another of their devices succeeded (see
    0020_notification_log_devices.sql).
    """
    row = conn.execute(
        f"""
        insert into notification_log_devices
            (notification_log_id, expo_push_token, status, expo_ticket_id, error)
        values (%s, %s, %s, %s, %s)
        returning {_DEVICE_COLUMNS}
        """,
        (notification_log_id, expo_push_token, status, expo_ticket_id, error),
    ).fetchone()
    assert row is not None
    return NotificationLogDevice.model_validate(row)


def list_devices_awaiting_reconciliation(
    conn: psycopg.Connection[DictRow], *, before: datetime.datetime
) -> list[NotificationLogDevice]:
    """MP-073: device rows a ticket was issued for but whose actual delivery outcome (Expo's
    receipt) has never been checked. `before` is the reconciliation job's own "now minus a buffer"
    — Expo's receipts aren't necessarily available the instant a ticket is issued, and `updated_at`
    is set the moment the row was recorded 'sent', so this only picks up rows old enough that a
    receipt is actually likely to exist yet (the ~30-minute-later follow-up from the technical
    spec's outbox diagram). A device row missing `expo_ticket_id` was never actually sent (the
    failed-send branch never gets one) and has nothing to reconcile against.
    """
    rows = conn.execute(
        f"""
        select {_DEVICE_COLUMNS} from notification_log_devices
        where status = 'sent' and expo_ticket_id is not null and updated_at < %s
        """,
        (before,),
    ).fetchall()
    return [NotificationLogDevice.model_validate(row) for row in rows]


def mark_device_status(
    conn: psycopg.Connection[DictRow], device_id: uuid.UUID, status: str
) -> NotificationLogDevice:
    row = conn.execute(
        f"""
        update notification_log_devices
        set status = %s, updated_at = now()
        where id = %s
        returning {_DEVICE_COLUMNS}
        """,
        (status, device_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"notification_log_devices row {device_id} not found")
    return NotificationLogDevice.model_validate(row)


def sync_notification_status_from_devices(
    conn: psycopg.Connection[DictRow], notification_log_id: uuid.UUID
) -> NotificationLog:
    """Rolls this notification's per-device outcomes (recorded above) up into the aggregate
    notification_log row the send pipeline's claim/SLO logic reads: 'delivered' if any device
    delivered, 'failed' only once every device has failed, otherwise left alone (still 'sent' —
    some device is still awaiting reconciliation). `delivered_at` is only ever set on the
    'delivered' transition, and only the first time — a second device delivering later must not
    push it forward, since app/services/notification_slo.py measures time-to-first-delivery.
    """
    row = conn.execute(
        f"""
        with device_rollup as (
            select
                bool_or(status = 'delivered') as any_delivered,
                bool_and(status = 'failed') as all_failed
            from notification_log_devices
            where notification_log_id = %s
        )
        update notification_log nl
        set status = case
                when device_rollup.any_delivered then 'delivered'
                when device_rollup.all_failed then 'failed'
                else nl.status
            end,
            delivered_at = case
                when device_rollup.any_delivered and nl.status <> 'delivered' then now()
                else nl.delivered_at
            end,
            updated_at = now()
        from device_rollup
        where nl.id = %s
        returning {", ".join(f"nl.{c.strip()}" for c in _COLUMNS.split(","))}
        """,
        (notification_log_id, notification_log_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"notification_log row {notification_log_id} not found")
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
