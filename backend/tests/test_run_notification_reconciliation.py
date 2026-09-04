"""MP-073: reconcile() unit tests against a real throwaway database (conftest.py's `conn` fixture)
— monkeypatches only the Expo network boundary, not the repository layer, since this script's own
value is entirely in wiring the two together correctly.

PR review fix: reconciliation now operates on per-device rows (notification_log_devices,
0020_notification_log_devices.sql), not a single ticket on the parent row, so a multi-device user's
every send gets its own receipt check — see test_a_mixed_multi_device_outcome_reconciles_each_
device_individually below for the case that motivated this.
"""

from __future__ import annotations

import datetime

import pytest

from app.repositories import notifications as notifications_repo
from scripts import run_notification_reconciliation


@pytest.fixture(autouse=True)
def clean_notification_log(conn):
    # reconcile() commits for real (mirrors production) — pg_dsn is a session-scoped database
    # shared with every other test file, and list_for_target_date isn't user-scoped, so a stale
    # committed row from an earlier test with the same (type, date) can leak into this one's
    # re-read. Same pattern as Phase 5's ingest_catalog tests: commit our own cleanup on both
    # sides rather than relying on the `conn` fixture's rollback-only teardown. Deleting
    # notification_log cascades to notification_log_devices (0020's on delete cascade).
    conn.execute("delete from notification_log")
    conn.commit()
    yield
    conn.execute("delete from notification_log")
    conn.commit()


def _future_cutoff() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=1)


def test_ok_receipt_marks_the_notification_delivered(conn, make_user, monkeypatch):
    user_id = make_user()
    notification = notifications_repo.upsert_pending(
        conn, user_id, "daily_reminder", datetime.date(2026, 8, 24)
    )
    notifications_repo.mark_status(conn, notification.id, "sent")
    notifications_repo.record_device_result(
        conn, notification.id, "ExponentPushToken[a]", "sent", expo_ticket_id="ticket-ok"
    )
    monkeypatch.setattr(
        run_notification_reconciliation,
        "get_expo_receipts",
        lambda ids, token: {"ticket-ok": {"status": "ok"}},
    )

    result = run_notification_reconciliation.reconcile(conn, None, before=_future_cutoff())

    assert result == run_notification_reconciliation.ReconciliationResult(
        delivered=1, failed=0, still_pending=0
    )
    reread = notifications_repo.list_for_target_date(
        conn, "daily_reminder", datetime.date(2026, 8, 24)
    )
    assert reread[0].status == "delivered"
    assert reread[0].delivered_at is not None


def test_error_receipt_marks_the_notification_failed(conn, make_user, monkeypatch):
    user_id = make_user()
    notification = notifications_repo.upsert_pending(
        conn, user_id, "week_ready", datetime.date(2026, 8, 24)
    )
    notifications_repo.mark_status(conn, notification.id, "sent")
    notifications_repo.record_device_result(
        conn, notification.id, "ExponentPushToken[a]", "sent", expo_ticket_id="ticket-bad"
    )
    monkeypatch.setattr(
        run_notification_reconciliation,
        "get_expo_receipts",
        lambda ids, token: {"ticket-bad": {"status": "error", "message": "DeviceNotRegistered"}},
    )

    result = run_notification_reconciliation.reconcile(conn, None, before=_future_cutoff())

    assert result == run_notification_reconciliation.ReconciliationResult(
        delivered=0, failed=1, still_pending=0
    )
    reread = notifications_repo.list_for_target_date(conn, "week_ready", datetime.date(2026, 8, 24))
    assert reread[0].status == "failed"


def test_a_missing_receipt_leaves_the_row_sent_for_a_later_run(conn, make_user, monkeypatch):
    user_id = make_user()
    notification = notifications_repo.upsert_pending(
        conn, user_id, "daily_reminder", datetime.date(2026, 8, 24)
    )
    notifications_repo.mark_status(conn, notification.id, "sent")
    notifications_repo.record_device_result(
        conn, notification.id, "ExponentPushToken[a]", "sent", expo_ticket_id="ticket-unknown"
    )
    monkeypatch.setattr(
        run_notification_reconciliation, "get_expo_receipts", lambda ids, token: {}
    )

    result = run_notification_reconciliation.reconcile(conn, None, before=_future_cutoff())

    assert result == run_notification_reconciliation.ReconciliationResult(
        delivered=0, failed=0, still_pending=1
    )
    reread = notifications_repo.list_for_target_date(
        conn, "daily_reminder", datetime.date(2026, 8, 24)
    )
    assert reread[0].status == "sent"


def test_nothing_awaiting_reconciliation_makes_no_receipts_call(conn, monkeypatch):
    def fail_if_called(ids, token):
        raise AssertionError("get_expo_receipts should not be called with nothing to reconcile")

    monkeypatch.setattr(run_notification_reconciliation, "get_expo_receipts", fail_if_called)

    result = run_notification_reconciliation.reconcile(conn, None, before=_future_cutoff())

    assert result == run_notification_reconciliation.ReconciliationResult(
        delivered=0, failed=0, still_pending=0
    )


def test_only_tickets_returned_by_the_receipts_call_are_updated(conn, make_user, monkeypatch):
    """Two notifications awaiting reconciliation; Expo only has a receipt for one this run."""
    user_id = make_user()
    ready = notifications_repo.upsert_pending(
        conn, user_id, "daily_reminder", datetime.date(2026, 8, 24)
    )
    notifications_repo.mark_status(conn, ready.id, "sent")
    notifications_repo.record_device_result(
        conn, ready.id, "ExponentPushToken[a]", "sent", expo_ticket_id="ticket-ready"
    )
    not_yet = notifications_repo.upsert_pending(
        conn, user_id, "daily_reminder", datetime.date(2026, 8, 25)
    )
    notifications_repo.mark_status(conn, not_yet.id, "sent")
    notifications_repo.record_device_result(
        conn, not_yet.id, "ExponentPushToken[a]", "sent", expo_ticket_id="ticket-not-yet"
    )
    monkeypatch.setattr(
        run_notification_reconciliation,
        "get_expo_receipts",
        lambda ids, token: {"ticket-ready": {"status": "ok"}},
    )

    result = run_notification_reconciliation.reconcile(conn, None, before=_future_cutoff())

    assert result == run_notification_reconciliation.ReconciliationResult(
        delivered=1, failed=0, still_pending=1
    )


def test_a_mixed_multi_device_outcome_reconciles_each_device_individually(
    conn, make_user, monkeypatch
):
    """MP-071 PR review fix: a user with two registered devices, one send succeeding and one
    failing outright — the failed device's attempt must stay auditable (its own row, its own
    status) rather than disappearing because the other device's send made the parent row read
    'sent'. Once the surviving device's ticket is reconciled as delivered, the parent rolls up to
    'delivered' even though one of its two devices never delivered at all.
    """
    user_id = make_user()
    notification = notifications_repo.upsert_pending(
        conn, user_id, "daily_reminder", datetime.date(2026, 8, 24)
    )
    notifications_repo.mark_status(conn, notification.id, "sent")
    notifications_repo.record_device_result(
        conn, notification.id, "ExponentPushToken[a]", "sent", expo_ticket_id="ticket-device-a"
    )
    notifications_repo.record_device_result(
        conn, notification.id, "ExponentPushToken[b]", "failed", error="DeviceNotRegistered"
    )
    monkeypatch.setattr(
        run_notification_reconciliation,
        "get_expo_receipts",
        lambda ids, token: {"ticket-device-a": {"status": "ok"}},
    )

    result = run_notification_reconciliation.reconcile(conn, None, before=_future_cutoff())

    assert result == run_notification_reconciliation.ReconciliationResult(
        delivered=1, failed=0, still_pending=0
    )
    reread = notifications_repo.list_for_target_date(
        conn, "daily_reminder", datetime.date(2026, 8, 24)
    )
    assert reread[0].status == "delivered"


def test_a_double_device_failure_rolls_the_parent_up_to_failed(conn, make_user, monkeypatch):
    user_id = make_user()
    notification = notifications_repo.upsert_pending(
        conn, user_id, "daily_reminder", datetime.date(2026, 8, 24)
    )
    notifications_repo.mark_status(conn, notification.id, "sent")
    notifications_repo.record_device_result(
        conn, notification.id, "ExponentPushToken[a]", "sent", expo_ticket_id="ticket-a"
    )
    notifications_repo.record_device_result(
        conn, notification.id, "ExponentPushToken[b]", "sent", expo_ticket_id="ticket-b"
    )
    monkeypatch.setattr(
        run_notification_reconciliation,
        "get_expo_receipts",
        lambda ids, token: {
            "ticket-a": {"status": "error", "message": "boom"},
            "ticket-b": {"status": "error", "message": "boom"},
        },
    )

    result = run_notification_reconciliation.reconcile(conn, None, before=_future_cutoff())

    assert result == run_notification_reconciliation.ReconciliationResult(
        delivered=0, failed=2, still_pending=0
    )
    reread = notifications_repo.list_for_target_date(
        conn, "daily_reminder", datetime.date(2026, 8, 24)
    )
    assert reread[0].status == "failed"
