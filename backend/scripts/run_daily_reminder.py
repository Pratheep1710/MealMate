"""MP-070: tomorrow-plan daily reminder job.

Invoked once a day (see .github/workflows/daily-reminder.yml, 20:00 IST) — not a job queue/worker
pool (explicitly out of v1 scope, docs/MP-001), just a scheduled script over a single DB
connection, same shape as backend/scripts/provision_ci_test_users.py.

For every user with at least one registered device (app/repositories/push_tokens.py): reads
tomorrow's *current* plan (post-edit/post-skip — app/repositories/plans.py's
get_day_plan_with_dishes), composes the "idea, not plan" copy (app/services/reminder_copy.py),
claims the notification_log row (app/jobs/entrypoints.py's run_daily_reminder_dispatch, idempotent),
and sends via Expo (app/services/push_dispatch.py) if app/jobs/entrypoints.py's
should_send_reminder says it's still worth sending.

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
from app.jobs.entrypoints import run_daily_reminder_dispatch, should_send_reminder
from app.logging import get_logger
from app.repositories import notifications as notifications_repo
from app.repositories import plans as plans_repo
from app.repositories import push_tokens as push_tokens_repo
from app.services.push_dispatch import PushSendError, send_expo_push
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

            notification = run_daily_reminder_dispatch(conn, user_id, target_date)
            if not should_send_reminder(notification):
                skipped += 1
                continue

            tokens = push_tokens_repo.list_tokens_for_user(conn, user_id)
            last_ticket_id: str | None = None
            for token in tokens:
                try:
                    last_ticket_id = send_expo_push(
                        token.expo_push_token, title, body, config.expo.access_token
                    )
                except (PushSendError, httpx.HTTPError) as exc:
                    logger.info(
                        "daily_reminder.send_failed", user_id=str(user_id), error=str(exc)
                    )

            # One attempt per run regardless of device count — a multi-device user's second and
            # third sends aren't retries of a failure, so they shouldn't consume the "one same-day
            # retry" budget should_send_reminder enforces.
            if last_ticket_id is not None:
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
