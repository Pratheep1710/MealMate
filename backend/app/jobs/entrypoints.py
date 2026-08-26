from __future__ import annotations

import datetime
import uuid

import psycopg
from psycopg.rows import DictRow

from app.logging import correlation_context, get_logger
from app.models import GenerationJob, NotificationLog
from app.repositories import jobs as jobs_repo
from app.repositories import notifications as notifications_repo

logger = get_logger(__name__)


def run_weekly_generation(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, week_start: datetime.date
) -> GenerationJob:
    """Claims (or returns the existing) generation_jobs row for this (user, week) — idempotent
    per the table's unique constraint — under correlation-scoped logging. The complete Phase 6
    path uses app/services/generation_engine.py; this lower-level helper remains the cheap
    idempotent ensure-row operation used by earlier callers and tests.
    """
    with correlation_context(user_id=str(user_id), week_start=week_start.isoformat()):
        job = jobs_repo.claim_or_create_job(conn, user_id, week_start)
        logger.info("generation_job.claimed", job_id=str(job.id), status=job.status)
        return job


def run_daily_reminder_dispatch(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, target_date: datetime.date
) -> NotificationLog:
    """Claims (or returns the existing) notification_log row for this (user, day) — idempotent per
    the table's unique constraint — under correlation-scoped logging. The actual Expo push send
    (outbox ticket dispatch, docs/MP-001 "Core") is M6 scope — see should_send_reminder below and
    backend/scripts/run_daily_reminder.py, this phase's implementation of that scope.
    """
    with correlation_context(user_id=str(user_id), correlation_id=target_date.isoformat()):
        notification = notifications_repo.upsert_pending(
            conn, user_id, "daily_reminder", target_date
        )
        logger.info(
            "notification.claimed",
            notification_id=str(notification.id),
            status=notification.status,
        )
        return notification


def should_send_reminder(notification: NotificationLog) -> bool:
    """Whether a claimed notification_log row is still worth sending: not if it already went out
    (`sent`/`delivered` — the claim's idempotency already prevents a duplicate row, this is the
    parallel guard against a duplicate *send* if the job is invoked twice), and not if it has
    already used up docs/MP-001's "one same-day retry" budget (one original attempt + one retry).
    """
    if notification.status in ("sent", "delivered"):
        return False
    return not (notification.status == "failed" and notification.attempt >= 2)
