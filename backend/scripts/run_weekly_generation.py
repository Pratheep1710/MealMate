"""Phase 6 daily 8 PM IST weekly-generation sweep."""

from __future__ import annotations

import datetime
import sys
from dataclasses import dataclass

from app.config import ConfigError, load_config
from app.db import connect
from app.logging import get_logger
from app.repositories import profiles as profiles_repo
from app.services.generation_context import build_generation_catalog
from app.services.generation_engine import run_generation_engine
from app.services.notification_dispatch import dispatch_week_ready
from app.services.openai_generation import OpenAIWeeklyMenuGenerator
from app.services.planning_trigger import compute_trigger, week_start_monday

logger = get_logger(__name__)
_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _today_ist() -> datetime.date:
    return datetime.datetime.now(_IST).date()


def _week_start_for_grocery_day(grocery_day_date: datetime.date) -> datetime.date:
    """Calendar-week anchor for the grocery-day occurrence that caused this trigger. Phase 9:
    delegates to planning_trigger.week_start_monday, the shared home for this now that the live
    /generation/trigger endpoint needs the exact same Monday-of-week computation.
    """
    return week_start_monday(grocery_day_date)


@dataclass(frozen=True)
class SweepResult:
    generated: int
    skipped: int
    failed: int
    notified: int


def run_sweep(conn, sweep_date: datetime.date, generator, access_token: str | None) -> SweepResult:
    generated = skipped = failed = notified = 0
    triggered = []
    for profile in profiles_repo.list_profiles(conn):
        try:
            decision = compute_trigger(sweep_date, profile.grocery_day, profile.planning_mode)
        except Exception as exc:
            conn.rollback()
            failed += 1
            logger.error(
                "weekly_generation.trigger_failed",
                user_id=str(profile.id),
                error_type=type(exc).__name__,
            )
            continue
        if decision.should_trigger:
            triggered.append((profile, decision))
        else:
            skipped += 1

    # The model-facing catalog is identical across users. Load it once and pass the immutable
    # tuple through each context instead of issuing five catalog queries for every profile.
    catalog = build_generation_catalog(conn) if triggered else ()

    for profile, decision in triggered:
        assert decision.grocery_day_date is not None
        week_start = _week_start_for_grocery_day(decision.grocery_day_date)
        try:
            outcome = run_generation_engine(
                conn,
                profile.id,
                week_start,
                generator,
                catalog=catalog,
            )
            if outcome is None:
                skipped += 1
                continue
            generated += 1
            if dispatch_week_ready(conn, outcome, access_token):
                notified += 1
        except Exception as exc:
            # Always restore the shared connection before advancing to the next profile. This is
            # deliberately redundant with the engine's rollback so errors in claim/dispatch or a
            # future call site cannot leave Postgres in transaction-aborted state.
            conn.rollback()
            failed += 1
            logger.error(
                "weekly_generation.profile_failed",
                user_id=str(profile.id),
                error_type=type(exc).__name__,
            )

    return SweepResult(generated, skipped, failed, notified)


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    sweep_date = _today_ist()
    generator = OpenAIWeeklyMenuGenerator(config.openai.api_key, config.openai.model)

    with connect(config) as conn:
        result = run_sweep(conn, sweep_date, generator, config.expo.access_token)

    logger.info(
        "weekly_generation.sweep_done",
        sweep_date=sweep_date.isoformat(),
        generated=result.generated,
        skipped=result.skipped,
        failed=result.failed,
        notified=result.notified,
    )
    print(
        f"Weekly generation sweep for {sweep_date}: generated={result.generated} "
        f"skipped={result.skipped} failed={result.failed} notified={result.notified}"
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
