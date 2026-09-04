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
import pytest
from psycopg.rows import DictRow, dict_row

from app.repositories import notifications as notifications_repo
from app.services import push_dispatch, reminder_claim


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


def test_claim_reminder_does_not_reclaim_after_a_single_failed_attempt(conn, make_user):
    """PR review fix: try_claim used to reclaim a 'failed' row while attempt < 2, on the old
    assumption that one claimed run makes exactly one real Expo attempt. Now that
    push_dispatch.send_expo_push_with_one_retry spends the *entire* same-evening retry budget
    (initial attempt + one retry) inside a single claimed call, a 'failed' row has nothing left to
    reclaim — a later run must not get a second bite.
    """
    user_id = make_user()
    target_date = datetime.date(2026, 8, 24)

    first = reminder_claim.claim_reminder(conn, user_id, target_date)
    assert first is not None
    notifications_repo.mark_status(conn, first.id, "failed", increment_attempt=True)

    second = reminder_claim.claim_reminder(conn, user_id, target_date)

    assert second is None


def test_claim_reminder_does_not_reclaim_after_a_double_failure_exhausts_the_retry_budget(
    conn, make_user, monkeypatch
):
    """End-to-end: the claim/job path invoked again after send_expo_push_with_one_retry has
    already made its two real Expo attempts (one initial + one retry, both within the first
    claimed call) and the row is marked failed — a second claim must return None, so a later
    scheduled/manual run can't draw two more attempts on top of those two (four total instead of
    the two MP-072's policy allows).
    """
    user_id = make_user()
    target_date = datetime.date(2026, 8, 24)

    first = reminder_claim.claim_reminder(conn, user_id, target_date)
    assert first is not None

    attempts: list[int] = []

    def fake_send(*args: object, **kwargs: object) -> str:
        attempts.append(1)
        raise push_dispatch.PushSendError("boom")

    monkeypatch.setattr(push_dispatch, "send_expo_push", fake_send)

    with pytest.raises(push_dispatch.PushSendError):
        push_dispatch.send_expo_push_with_one_retry("token", "title", "body", None)
    assert len(attempts) == 2  # the entire same-evening budget, spent within this one claim

    notifications_repo.mark_status(conn, first.id, "failed", increment_attempt=True)

    second = reminder_claim.claim_reminder(conn, user_id, target_date)

    assert second is None


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

    try:
        winners = [r for r in results if r is not None]
        assert len(winners) == 1
        assert winners[0].status == "processing"
    finally:
        # autocommit connections bypass the `conn` fixture's rollback teardown, so this row
        # would otherwise persist for the rest of the pytest session (pg_dsn is session-scoped)
        # — list_for_target_date's (type, date) scoping isn't user-scoped, so a leftover row
        # here previously inflated test_list_for_target_date_scopes_by_type_and_date's count.
        with psycopg.connect(**pg_dsn, autocommit=True, row_factory=dict_row) as cleanup_conn:
            cleanup_conn.execute(
                "delete from notification_log where user_id = %s and target_date = %s",
                (user_id, target_date),
            )
