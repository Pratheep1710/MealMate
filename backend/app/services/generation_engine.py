"""Phase 6 weekly-generation orchestration: claim, retry, fallback, persist, finish."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass

import psycopg
from psycopg.rows import DictRow

from app.logging import correlation_context, get_logger
from app.models import GenerationJob
from app.repositories import jobs as jobs_repo
from app.services.generation_claim import claim_job
from app.services.generation_context import CatalogGroup, build_generation_context
from app.services.generation_models import GeneratedPlan, plan_from_menu
from app.services.generation_prompt import build_generation_prompt
from app.services.menu_validation import ValidationIssue, validate_menu
from app.services.openai_generation import GenerationProviderError, WeeklyMenuGenerator
from app.services.plan_persistence import PersistenceResult, persist_generated_plan
from app.services.rule_based_fallback import build_fallback_plan

logger = get_logger(__name__)


@dataclass(frozen=True)
class GenerationOutcome:
    job: GenerationJob
    plan: GeneratedPlan
    persistence: PersistenceResult
    validation_issues: tuple[ValidationIssue, ...]


def _claim(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    week_start: datetime.date,
    start_date: datetime.date | None,
) -> GenerationJob | None:
    claimed = claim_job(conn, user_id, week_start)
    if claimed is not None:
        return claimed
    existing = jobs_repo.claim_or_create_job(conn, user_id, week_start)
    if start_date is not None:
        return jobs_repo.try_restart_processing(conn, existing.id)
    return jobs_repo.try_retry_failed(conn, existing.id)


def _run_claimed_generation(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    week_start: datetime.date,
    job: GenerationJob,
    generator: WeeklyMenuGenerator,
    *,
    start_date: datetime.date | None,
    catalog: tuple[CatalogGroup, ...] | None,
) -> GenerationOutcome:
    context = build_generation_context(
        conn,
        user_id,
        week_start,
        start_date=start_date,
        catalog=catalog,
    )
    retry_issues: tuple[ValidationIssue, ...] = ()
    selected_plan: GeneratedPlan | None = None

    for attempt in range(2):
        jobs_repo.update_job_status(
            conn,
            job.id,
            "processing",
            last_error=None,
            increment_attempt=True,
        )
        conn.commit()
        prompt = build_generation_prompt(context, retry_issues=retry_issues)
        try:
            menu = generator.generate(prompt)
        except GenerationProviderError as exc:
            retry_issues = (
                ValidationIssue(
                    "combo_template",
                    f"provider output could not be parsed on attempt {attempt + 1}: {exc}",
                ),
            )
            logger.warning(
                "weekly_generation.provider_failure",
                attempt=attempt + 1,
                error_type=type(exc).__name__,
            )
            continue

        validation = validate_menu(menu, context)
        if validation.is_valid:
            selected_plan = plan_from_menu(menu)
            retry_issues = ()
            break
        retry_issues = validation.issues
        logger.warning(
            "weekly_generation.validation_failed",
            attempt=attempt + 1,
            issue_codes=[issue.code for issue in validation.issues],
        )

    if selected_plan is None:
        selected_plan = build_fallback_plan(context)
        logger.info(
            "weekly_generation.fallback_selected",
            issue_codes=[issue.code for issue in retry_issues],
        )

    persistence = persist_generated_plan(
        conn,
        user_id,
        context.profile,
        selected_plan,
        context.available_ingredient_ids,
    )
    completed = jobs_repo.update_job_status(
        conn,
        job.id,
        "done",
        last_error=(
            None
            if selected_plan.source == "openai"
            else "fallback after model/provider validation failures"
        ),
    )
    conn.commit()
    logger.info(
        "weekly_generation.done",
        source=selected_plan.source,
        item_count=len(selected_plan.items),
    )
    return GenerationOutcome(
        job=completed,
        plan=selected_plan,
        persistence=persistence,
        validation_issues=retry_issues,
    )


def _record_failure(conn: psycopg.Connection[DictRow], job: GenerationJob, failure: str) -> None:
    """Best-effort terminal status update without masking or preserving an aborted transaction."""
    try:
        jobs_repo.update_job_status(conn, job.id, "failed", last_error=failure)
        conn.commit()
    except Exception as status_exc:
        conn.rollback()
        logger.error(
            "weekly_generation.failure_status_update_failed",
            error_type=type(status_exc).__name__,
        )


def run_generation_engine(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    week_start: datetime.date,
    generator: WeeklyMenuGenerator,
    *,
    start_date: datetime.date | None = None,
    catalog: tuple[CatalogGroup, ...] | None = None,
) -> GenerationOutcome | None:
    """Run one claimed generation, returning ``None`` when idempotency says it already ran."""
    job: GenerationJob | None = None
    with correlation_context(user_id=str(user_id), week_start=week_start.isoformat()):
        try:
            job = _claim(conn, user_id, week_start, start_date)
            if job is None:
                return None
            conn.commit()  # release the atomic claim before the external model call
            with correlation_context(job_id=str(job.id)):
                return _run_claimed_generation(
                    conn,
                    user_id,
                    week_start,
                    job,
                    generator,
                    start_date=start_date,
                    catalog=catalog,
                )
        except Exception as exc:
            conn.rollback()
            failure = type(exc).__name__
            if job is not None:
                _record_failure(conn, job, failure)
            logger.error("weekly_generation.failed", error_type=failure)
            raise
