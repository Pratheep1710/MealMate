"""MP-029 job entrypoints — idempotent claim behavior against the real schema."""

from __future__ import annotations

import datetime

from app.jobs.entrypoints import (
    run_daily_reminder_dispatch,
    run_weekly_generation,
    should_send_reminder,
)
from app.models import NotificationLog


def test_run_weekly_generation_is_idempotent(conn, make_user):
    user_id = make_user()
    week_start = datetime.date(2026, 8, 24)

    first = run_weekly_generation(conn, user_id, week_start)
    second = run_weekly_generation(conn, user_id, week_start)

    assert first.id == second.id
    assert first.status == "pending"


def test_run_daily_reminder_dispatch_is_idempotent(conn, make_user):
    user_id = make_user()
    target_date = datetime.date(2026, 8, 24)

    first = run_daily_reminder_dispatch(conn, user_id, target_date)
    second = run_daily_reminder_dispatch(conn, user_id, target_date)

    assert first.id == second.id
    assert first.notification_type == "daily_reminder"


def _notification(*, status: str, attempt: int = 0) -> NotificationLog:
    import uuid

    now = datetime.datetime.now(datetime.UTC)
    return NotificationLog(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        notification_type="daily_reminder",
        target_date=datetime.date(2026, 8, 24),
        status=status,
        expo_ticket_id=None,
        attempt=attempt,
        created_at=now,
        updated_at=now,
        delivered_at=None,
    )


def test_should_send_reminder_sends_a_fresh_pending_claim():
    assert should_send_reminder(_notification(status="pending")) is True


def test_should_send_reminder_allows_one_retry_after_a_failure():
    assert should_send_reminder(_notification(status="failed", attempt=1)) is True


def test_should_send_reminder_stops_after_the_retry_budget_is_used():
    assert should_send_reminder(_notification(status="failed", attempt=2)) is False


def test_should_send_reminder_never_resends_once_sent():
    assert should_send_reminder(_notification(status="sent", attempt=1)) is False


def test_should_send_reminder_never_resends_once_delivered():
    assert should_send_reminder(_notification(status="delivered", attempt=1)) is False
