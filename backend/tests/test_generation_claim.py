"""MP-033 generation job claim (app/services/generation_claim.py).

The sequential test below is a sanity check; the real guarantee MP-033 asks for — "repeated
scheduler invocation does not generate the same user/week twice" under near-simultaneous calls —
is only actually exercised by test_claim_job_under_a_real_race_only_one_caller_wins, which opens
two independent Postgres connections (separate sessions, like two scheduler processes would be)
and fires both claims at the same time via a thread barrier.
"""

from __future__ import annotations

import datetime
import threading
import uuid

import psycopg
from psycopg.rows import DictRow, dict_row

from app.services import generation_claim


def _make_user(conn: psycopg.Connection[DictRow], user_id: uuid.UUID) -> None:
    conn.execute("insert into auth.users (id) values (%s)", (user_id,))
    conn.execute(
        "insert into user_profiles (id, dietary_restrictions, grocery_day) values (%s, %s, %s)",
        (user_id, [], "monday"),
    )


def test_claim_job_sequential_double_call_only_returns_once(conn, make_user):
    user_id = make_user()
    week_start = datetime.date(2026, 8, 24)

    first = generation_claim.claim_job(conn, user_id, week_start)
    second = generation_claim.claim_job(conn, user_id, week_start)

    assert first is not None
    assert first.status == "processing"
    assert second is None


def test_claim_job_under_a_real_race_only_one_caller_wins(pg_dsn: dict[str, str | int]) -> None:
    user_id = uuid.uuid4()
    week_start = datetime.date(2026, 8, 24)

    with psycopg.connect(**pg_dsn, autocommit=True, row_factory=dict_row) as setup_conn:
        _make_user(setup_conn, user_id)

    results: list[object] = [None, None]
    barrier = threading.Barrier(2)

    def _attempt(index: int) -> None:
        with psycopg.connect(**pg_dsn, autocommit=True, row_factory=dict_row) as race_conn:
            barrier.wait()
            results[index] = generation_claim.claim_job(race_conn, user_id, week_start)

    threads = [threading.Thread(target=_attempt, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert winners[0].status == "processing"
