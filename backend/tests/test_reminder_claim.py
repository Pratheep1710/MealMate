"""MP-070 review fix (PR #10): daily-reminder send claim (app/services/reminder_claim.py).

The sequential tests below are sanity checks; the real guarantee — "two overlapping runs never
both send the same reminder" — is only actually exercised by
test_claim_reminder_under_a_real_race_only_one_caller_wins, which opens two independent Postgres
connections (like a scheduled run and a manual workflow_dispatch overlapping) and fires both
claims at the same time via a thread barrier, mirroring test_generation_claim.py's pattern.
"""

from __future__ import annotations

import datetime
import threading
import uuid

import psycopg
from psycopg.rows import DictRow, dict_row

from app.repositories import notifications as notifications_repo
from app.services import reminder_claim


def _make_user(conn: psycopg.Connection[DictRow], user_id: uuid.UUID) -> None:
    conn.execute("insert into auth.users (id) values (%s)", (user_id,))
    conn.execute(
        "insert into user_profiles (id, dietary_restrictions, grocery_day) values (%s, %s, %s)",
        (user_id, [], "monday"),
    )


def test_claim_reminder_sequential_double_call_only_returns_once(conn, make_user):
    user_id = make_user()
    target_date = datetime.date(2026, 8, 24)

    first = reminder_claim.claim_reminder(conn, user_id, target_date)
    second = reminder_claim.claim_reminder(conn, user_id, target_date)

    assert first is not None
    assert first.status == "processing"
    assert second is None


def test_claim_reminder_reclaims_after_a_failed_attempt_within_the_retry_budget(conn, make_user):
    user_id = make_user()
    target_date = datetime.date(2026, 8, 24)

    first = reminder_claim.claim_reminder(conn, user_id, target_date)
    assert first is not None
    notifications_repo.mark_status(conn, first.id, "failed", increment_attempt=True)

    second = reminder_claim.claim_reminder(conn, user_id, target_date)

    assert second is not None
    assert second.status == "processing"
    assert second.attempt == 1


def test_claim_reminder_does_not_reclaim_after_the_retry_budget_is_used(conn, make_user):
    user_id = make_user()
    target_date = datetime.date(2026, 8, 24)

    first = reminder_claim.claim_reminder(conn, user_id, target_date)
    assert first is not None
    notifications_repo.mark_status(conn, first.id, "failed", increment_attempt=True)
    second = reminder_claim.claim_reminder(conn, user_id, target_date)
    assert second is not None
    notifications_repo.mark_status(conn, second.id, "failed", increment_attempt=True)

    third = reminder_claim.claim_reminder(conn, user_id, target_date)

    assert third is None


def test_claim_reminder_never_reclaims_once_sent(conn, make_user):
    user_id = make_user()
    target_date = datetime.date(2026, 8, 24)

    first = reminder_claim.claim_reminder(conn, user_id, target_date)
    assert first is not None
    notifications_repo.mark_status(conn, first.id, "sent", increment_attempt=True)

    second = reminder_claim.claim_reminder(conn, user_id, target_date)

    assert second is None


def test_claim_reminder_under_a_real_race_only_one_caller_wins(
    pg_dsn: dict[str, str | int],
) -> None:
    user_id = uuid.uuid4()
    target_date = datetime.date(2026, 8, 24)

    with psycopg.connect(**pg_dsn, autocommit=True, row_factory=dict_row) as setup_conn:
        _make_user(setup_conn, user_id)

    results: list[object] = [None, None]
    barrier = threading.Barrier(2)

    def _attempt(index: int) -> None:
        with psycopg.connect(**pg_dsn, autocommit=True, row_factory=dict_row) as race_conn:
            barrier.wait()
            results[index] = reminder_claim.claim_reminder(race_conn, user_id, target_date)

    threads = [threading.Thread(target=_attempt, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert winners[0].status == "processing"
