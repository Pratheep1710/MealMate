"""MP-070: tomorrow-plan daily reminder job.

Invoked once a day (see .github/workflows/daily-reminder.yml, 20:00 IST) — not a job queue/worker
pool (explicitly out of v1 scope, docs/MP-001), just a scheduled script over a single DB
connection, same shape as backend/scripts/provision_ci_test_users.py.

For every user with at least one registered device (app/repositories/push_tokens.py): reads
tomorrow's *current* plan (post-edit/post-skip — app/repositories/plans.py's
get_day_plan_with_dishes), composes the "idea, not plan" copy (app/services/reminder_copy.py),
and atomically claims the notification_log row (app/services/reminder_claim.py) before sending via
Expo (app/services/push_dispatch.py) — the claim is what lets two overlapping runs (scheduled +
manual, or two retried Actions jobs) coexist without both sending the same reminder.

Usage:
  cd backend && python scripts/run_daily_reminder.py
Reads the same SUPABASE_*/EXPO_* env vars as the rest of the app (app/config.py).
"""

from __future__ import annotations

import datetime
import sys

import httpx

from app.config import ConfigError, load_config
from app.db import connect
from app.logging import get_logger
from app.repositories import notifications as notifications_repo
from app.repositories import plans as plans_repo
from app.repositories import push_tokens as push_tokens_repo
from app.services.push_dispatch import PushSendError, send_expo_push_with_one_retry
from app.services.reminder_claim import claim_reminder
from app.services.reminder_copy import compose_reminder

logger = get_logger(__name__)

_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _tomorrow_ist() -> datetime.date:
    return datetime.datetime.now(_IST).date() + datetime.timedelta(days=1)


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    target_date = _tomorrow_ist()
    sent = 0
    skipped = 0
    failed = 0

    with connect(config) as conn:
        user_ids = push_tokens_repo.list_users_with_tokens(conn)
        logger.info(
            "daily_reminder.start",
            target_date=target_date.isoformat(),
            user_count=len(user_ids),
        )

        for user_id in user_ids:
            day_plan = plans_repo.get_day_plan_with_dishes(conn, user_id, target_date)
            composed = compose_reminder(day_plan)
            if composed is None:
                skipped += 1
                continue
            title, body = composed

            notification = claim_reminder(conn, user_id, target_date)
            conn.commit()  # release the 'processing' claim's row lock before the Expo HTTP call
            if notification is None:
                skipped += 1
                continue

            tokens = push_tokens_repo.list_tokens_for_user(conn, user_id)
            last_ticket_id: str | None = None
            any_sent = False
            for token in tokens:
                try:
                    ticket_id = send_expo_push_with_one_retry(
                        token.expo_push_token, title, body, config.expo.access_token
                    )
                except (PushSendError, httpx.HTTPError) as exc:
                    logger.info(
                        "daily_reminder.send_failed", user_id=str(user_id), error=str(exc)
                    )
                    # PR review fix (MP-071): record this device's own failed attempt rather than
                    # letting it disappear when another of the user's devices succeeds below.
                    notifications_repo.record_device_result(
                        conn, notification.id, token.expo_push_token, "failed", error=str(exc)
                    )
                    continue
                notifications_repo.record_device_result(
                    conn, notification.id, token.expo_push_token, "sent", expo_ticket_id=ticket_id
                )
                last_ticket_id = ticket_id
                any_sent = True

            # One attempt per run regardless of device count — a multi-device user's second and
            # third sends aren't retries of a failure, so they shouldn't consume the "one same-day
            # retry" budget notifications_repo.try_claim enforces. expo_ticket_id on the parent row
            # is now purely informational (one representative ticket) — reconciliation reads the
            # per-device rows recorded above, not this one.
            if any_sent:
                notifications_repo.mark_status(
                    conn,
                    notification.id,
                    "sent",
                    expo_ticket_id=last_ticket_id,
                    increment_attempt=True,
                )
                sent += 1
            else:
                notifications_repo.mark_status(
                    conn, notification.id, "failed", increment_attempt=True
                )
                failed += 1
            conn.commit()

    logger.info("daily_reminder.done", sent=sent, skipped=skipped, failed=failed)
    print(f"Daily reminder run for {target_date}: sent={sent} skipped={skipped} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
