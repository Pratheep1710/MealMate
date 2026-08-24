"""MP-033: generation job claim — the idempotency gate every scheduled model call must pass
before calling the LLM (docs/MP-001 "Weekly batch generation (one LLM call/week/user)"). Composes
MP-031's claim_or_create_job (ensure the row exists) with an atomic pending -> processing
transition, so a second near-simultaneous scheduler invocation for the same user/week is told not
to call the model, rather than generating the same week twice.
"""

from __future__ import annotations

import datetime
import uuid

import psycopg
from psycopg.rows import DictRow

from app.models import GenerationJob
from app.repositories import jobs as jobs_repo


def claim_job(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, week_start: datetime.date
) -> GenerationJob | None:
    """Returns the job (status='processing') if this call won the claim and should proceed to
    call the model; returns None if the job for this user/week was already claimed, in progress,
    or finished — the caller must not call the model in that case.
    """
    job = jobs_repo.claim_or_create_job(conn, user_id, week_start)
    return jobs_repo.try_start_processing(conn, job.id)
