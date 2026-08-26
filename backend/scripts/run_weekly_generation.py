"""Phase 6 daily 8 PM IST weekly-generation sweep."""

from __future__ import annotations

import datetime
import sys

import httpx

from app.config import ConfigError, load_config
from app.db import connect
from app.logging import get_logger
from app.repositories import notifications as notifications_repo
from app.repositories import profiles as profiles_repo
from app.repositories import push_tokens as push_tokens_repo
from app.services.generation_engine import GenerationOutcome, run_generation_engine
from app.services.openai_generation import OpenAIWeeklyMenuGenerator
from app.services.planning_trigger import compute_trigger
from app.services.push_dispatch import PushSendError, send_expo_push

logger = get_logger(__name__)
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _today_ist() -> datetime.date:
    return datetime.datetime.now(_IST).date()


def _next_monday(after: datetime.date) -> datetime.date:
    days_ahead = (-after.weekday()) % 7
    return after + datetime.timedelta(days=days_ahead or 7)


def _dispatch_week_ready(
    conn,
    outcome: GenerationOutcome,
    access_token: str | None,
) -> bool:
    notification = notifications_repo.try_claim(conn, outcome.persistence.notification.id)
    conn.commit()
    if notification is None:
        return False

    tokens = push_tokens_repo.list_tokens_for_user(conn, outcome.job.user_id)
    last_ticket_id: str | None = None
    for token in tokens:
        try:
            last_ticket_id = send_expo_push(
                token.expo_push_token,
                "Your week is ready",
                "Your meal ideas and grocery list are ready to review.",
                access_token,
            )
        except (PushSendError, httpx.HTTPError) as exc:
            logger.warning("week_ready.send_failed", error_type=type(exc).__name__)

    if last_ticket_id is None:
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


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    sweep_date = _today_ist()
    week_start = _next_monday(sweep_date)
    generator = OpenAIWeeklyMenuGenerator(config.openai.api_key, config.openai.model)
    generated = skipped = failed = notified = 0

    with connect(config) as conn:
        for profile in profiles_repo.list_profiles(conn):
            decision = compute_trigger(sweep_date, profile.grocery_day, profile.planning_mode)
            if not decision.should_trigger:
                skipped += 1
                continue
            try:
                outcome = run_generation_engine(conn, profile.id, week_start, generator)
                if outcome is None:
                    skipped += 1
                    continue
                generated += 1
                if _dispatch_week_ready(conn, outcome, config.expo.access_token):
                    notified += 1
            except Exception as exc:
                failed += 1
                logger.error(
                    "weekly_generation.profile_failed",
                    user_id=str(profile.id),
                    error_type=type(exc).__name__,
                )

    logger.info(
        "weekly_generation.sweep_done",
        sweep_date=sweep_date.isoformat(),
        generated=generated,
        skipped=skipped,
        failed=failed,
        notified=notified,
    )
    print(
        f"Weekly generation sweep for {sweep_date}: generated={generated} skipped={skipped} "
        f"failed={failed} notified={notified}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
