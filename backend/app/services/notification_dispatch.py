"""Phase 9 (MP-092/093/094): the "your week is ready" push dispatch, extracted from
backend/scripts/run_weekly_generation.py (where it was previously a private, sweep-only helper)
so the new live /generation/trigger endpoint can call the exact same function — not a second,
duplicated implementation. Without this, an onboarding-triggered generation would call
run_generation_engine successfully but its notification_log row would sit 'pending' forever:
nothing else ever claims and sends it.
"""

from __future__ import annotations

import httpx
import psycopg
from psycopg.rows import DictRow

from app.logging import get_logger
from app.repositories import notifications as notifications_repo
from app.repositories import push_tokens as push_tokens_repo
from app.services.generation_engine import GenerationOutcome
from app.services.push_dispatch import PushSendError, send_expo_push_with_one_retry

logger = get_logger(__name__)


def dispatch_week_ready(
    conn: psycopg.Connection[DictRow],
    outcome: GenerationOutcome,
    access_token: str | None,
) -> bool:
    notification = notifications_repo.try_claim(conn, outcome.persistence.notification.id)
    conn.commit()
    if notification is None:
        return False

    tokens = push_tokens_repo.list_tokens_for_user(conn, outcome.job.user_id)
    last_ticket_id: str | None = None
    any_sent = False
    for token in tokens:
        try:
            ticket_id = send_expo_push_with_one_retry(
                token.expo_push_token,
                "Your week is ready",
                "Your meal ideas and grocery list are ready to review.",
                access_token,
            )
        except (PushSendError, httpx.HTTPError) as exc:
            logger.warning("week_ready.send_failed", error_type=type(exc).__name__)
            # PR review fix (MP-071): audit this device's failure individually — the weekly sender
            # had the same "last ticket wins" gap as the daily reminder's.
            notifications_repo.record_device_result(
                conn, notification.id, token.expo_push_token, "failed", error=str(exc)
            )
            continue
        notifications_repo.record_device_result(
            conn, notification.id, token.expo_push_token, "sent", expo_ticket_id=ticket_id
        )
        last_ticket_id = ticket_id
        any_sent = True

    if not any_sent:
        notifications_repo.mark_status(conn, notification.id, "failed", increment_attempt=True)
        conn.commit()
        return False
    notifications_repo.mark_status(
        conn,
        notification.id,
        "sent",
        expo_ticket_id=last_ticket_id,
        increment_attempt=True,
    )
    conn.commit()
    return True
