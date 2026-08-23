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
    per the table's unique constraint — under correlation-scoped logging. The candidate-filtered
    generation call itself is M4 scope; this stops at a claimed job row.
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
    (outbox ticket dispatch, docs/MP-001 "Core") is M6 scope; this stops at a claimed 'pending' row.
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
