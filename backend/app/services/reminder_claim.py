"""MP-070 review fix (PR #10): daily-reminder send claim — the idempotency gate every reminder
send must pass, mirroring app/services/generation_claim.py's pending -> processing pattern.
Composes app/jobs/entrypoints.py's run_daily_reminder_dispatch (ensure the notification_log row
exists) with notifications_repo.try_claim's atomic status transition, so a second near-simultaneous
run (scheduled + manual, or two retried Actions jobs) is told not to call Expo's push API, rather
than sending the same reminder twice.
"""

from __future__ import annotations

import datetime
import uuid

import psycopg
from psycopg.rows import DictRow

from app.jobs.entrypoints import run_daily_reminder_dispatch
from app.models import NotificationLog
from app.repositories import notifications as notifications_repo


def claim_reminder(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, target_date: datetime.date
) -> NotificationLog | None:
    """Returns the notification_log row (status='processing') if this call won the claim and
    should proceed to send; returns None if the row was already sent/delivered, claimed by a
    concurrent run, or already failed (the one same-evening retry budget is spent entirely inside
    a single claimed call — see notifications_repo.try_claim) — the caller must not call Expo in
    that case.
    """
    notification = run_daily_reminder_dispatch(conn, user_id, target_date)
    return notifications_repo.try_claim(conn, notification.id)
