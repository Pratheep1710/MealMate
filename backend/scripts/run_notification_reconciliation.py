"""MP-073: Expo receipt reconciliation — the follow-up half of the outbox pattern (technical spec
§2.2's diagram: "Follow-up job ~30 min later: reconcile Expo receipts" -> "notification_log:
delivered / failed"). A ticket from `send_expo_push` only confirms Expo *accepted* the push for
delivery, not that a device actually received it — this job is what turns "sent" into a real
"delivered" or "failed" outcome, for every notification type (daily_reminder and week_ready alike).

Meant to run on its own schedule, comfortably after both daily sweeps (see
.github/workflows/notification-reconciliation.yml) — not chained onto either sweep directly, since
a receipt genuinely isn't ready the instant a ticket is issued.

Usage:
  cd backend && python scripts/run_notification_reconciliation.py
Reads the same SUPABASE_*/EXPO_* env vars as the rest of the app (app/config.py).
"""

from __future__ import annotations

import datetime
import sys
import uuid
from dataclasses import dataclass

from app.config import ConfigError, load_config
from app.db import connect
from app.logging import get_logger
from app.repositories import notifications as notifications_repo
from app.services.push_dispatch import get_expo_receipts

logger = get_logger(__name__)

_RECONCILIATION_BUFFER = datetime.timedelta(minutes=25)


@dataclass(frozen=True)
class ReconciliationResult:
    delivered: int
    failed: int
    still_pending: int


def reconcile(conn, access_token: str | None, *, before: datetime.datetime) -> ReconciliationResult:
    """PR review fix (MP-071/073): reconciles per-device rows (0020_notification_log_devices.sql),
    not the single last-ticket-wins column on the parent notification_log row — a multi-device
    user's every send gets its own receipt check. Each parent notification whose devices were
    touched this run is then rolled up (any device delivered -> 'delivered'; every device failed ->
    'failed'; otherwise left 'sent' for a later run), so the aggregate status/SLO reads on
    notification_log stay correct without a caller having to reconcile devices itself.
    """
    pending = notifications_repo.list_devices_awaiting_reconciliation(conn, before=before)
    if not pending:
        return ReconciliationResult(delivered=0, failed=0, still_pending=0)

    by_ticket = {device.expo_ticket_id: device for device in pending if device.expo_ticket_id}
    receipts = get_expo_receipts(list(by_ticket.keys()), access_token)

    delivered = failed = still_pending = 0
    touched_notification_ids: set[uuid.UUID] = set()
    for ticket_id, device in by_ticket.items():
        receipt = receipts.get(ticket_id)
        if receipt is None:
            # Not yet available from Expo — leave 'sent' for a later run rather than guessing.
            still_pending += 1
            continue
        status = "delivered" if receipt.get("status") == "ok" else "failed"
        notifications_repo.mark_device_status(conn, device.id, status)
        touched_notification_ids.add(device.notification_log_id)
        if status == "delivered":
            delivered += 1
        else:
            failed += 1
        conn.commit()

    for notification_id in touched_notification_ids:
        notifications_repo.sync_notification_status_from_devices(conn, notification_id)
        conn.commit()

    return ReconciliationResult(delivered=delivered, failed=failed, still_pending=still_pending)


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    before = datetime.datetime.now(datetime.UTC) - _RECONCILIATION_BUFFER
    with connect(config) as conn:
        logger.info("notification_reconciliation.start")
        result = reconcile(conn, config.expo.access_token, before=before)

    logger.info(
        "notification_reconciliation.done",
        delivered=result.delivered,
        failed=result.failed,
        still_pending=result.still_pending,
    )
    print(
        f"Notification reconciliation: delivered={result.delivered} failed={result.failed} "
        f"still_pending={result.still_pending}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
