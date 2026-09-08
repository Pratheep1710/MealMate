"""Phase 9 (MP-092/093/094): the live FastAPI endpoints the mobile client calls right after
onboarding. Both are thin: all the real work (auth, claim, eligibility, fallback selection) is
delegated to existing modules — see app/auth.py, app/services/generation_engine.py,
app/services/instant_fallback.py, app/services/notification_dispatch.py.
"""

from __future__ import annotations

import datetime
import uuid

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from psycopg.rows import DictRow
from pydantic import BaseModel

from app.auth import get_current_user_id
from app.config import AppConfig
from app.db import connect
from app.deps import get_config, get_db
from app.repositories import profiles as profiles_repo
from app.services.generation_engine import run_generation_engine
from app.services.instant_fallback import build_instant_fallback
from app.services.notification_dispatch import dispatch_week_ready
from app.services.openai_generation import OpenAIWeeklyMenuGenerator
from app.services.planning_trigger import compute_first_plan_start, week_start_monday

router = APIRouter()


def _today_ist() -> datetime.date:
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return datetime.datetime.now(ist).date()


def _run_and_notify(config: AppConfig, user_id: uuid.UUID, first_plan_start: datetime.date) -> None:
    """The actual background work — a fresh connection of its own (BackgroundTasks run before
    yield-dependency cleanup, so reusing the request's connection would technically work, but a
    dedicated one here keeps this function independently callable/testable without threading the
    request's connection through it).

    `start_date=first_plan_start`, not `week_start` — first_plan_start may be mid-week (the same
    off-cycle/partial-week mechanism `build_generation_context`'s own `start_date` param already
    supports for "regenerate remaining week"); passing the Monday instead would silently ask for
    the whole week starting from a date that may be in the past relative to when the user should
    actually start.
    """
    week_start = week_start_monday(first_plan_start)
    generator = OpenAIWeeklyMenuGenerator(config.openai.api_key, config.openai.model)
    with connect(config) as conn:
        outcome = run_generation_engine(
            conn, user_id, week_start, generator, start_date=first_plan_start
        )
        if outcome is not None:
            dispatch_week_ready(conn, outcome, config.expo.access_token)


class TriggerResponse(BaseModel):
    week_start: datetime.date


@router.post("/generation/trigger", status_code=202)
def trigger_generation(
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID = Depends(get_current_user_id),
    conn: psycopg.Connection[DictRow] = Depends(get_db),
    config: AppConfig = Depends(get_config),
) -> TriggerResponse:
    """MP-094: fires the exact same run_generation_engine (MP-040) through the exact same
    MP-033 atomic claim, right after onboarding — not a new trigger path. Idempotent for free: a
    same-evening 8 PM sweep for this user/week is simply told "already claimed" by the
    (user_id, week_start) unique constraint + conditional UPDATE inside _claim/try_start_processing;
    neither caller needs to know about the other.
    """
    profile = profiles_repo.get_profile(conn, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="no profile found for this user")

    first_plan_start = compute_first_plan_start(
        _today_ist(), profile.grocery_day, profile.planning_mode
    )
    week_start = week_start_monday(first_plan_start)

    # The real generation call is slow (an LLM round trip) — schedule it and return immediately
    # rather than making onboarding wait on it. MP-092's own screen state is what the mobile
    # client actually watches to know when this finished; this response is not that signal.
    background_tasks.add_task(_run_and_notify, config, user_id, first_plan_start)
    return TriggerResponse(week_start=week_start)


class InstantFallbackItem(BaseModel):
    day: datetime.date
    slot: str
    item_type: str
    dish_id: uuid.UUID | None
    dish_name: str | None


@router.get("/plan/instant-fallback")
def get_instant_fallback(
    user_id: uuid.UUID = Depends(get_current_user_id),
    conn: psycopg.Connection[DictRow] = Depends(get_db),
) -> list[InstantFallbackItem]:
    """MP-093: no LLM call, no job claim, no persistence — see
    app/services/instant_fallback.py for the reused-not-reimplemented eligibility path.
    """
    fallback = build_instant_fallback(conn, user_id, _today_ist())
    return [
        InstantFallbackItem(
            day=item.day,
            slot=item.slot,
            item_type=item.item_type,
            dish_id=item.dish_id,
            dish_name=fallback.dishes_by_id[item.dish_id].name if item.dish_id else None,
        )
        for item in fallback.items
    ]
