"""MP-029 job entrypoints — idempotent claim behavior against the real schema."""

from __future__ import annotations

import datetime

from app.jobs.entrypoints import run_daily_reminder_dispatch, run_weekly_generation


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
