"""MP-031: generation_jobs — the weekly-generation job's own bookkeeping.

`claim_or_create_job` is the idempotency guarantee unique(user_id, week_start) exists for: a
second call for the same week returns the existing row instead of erroring or double-queuing
work (docs/MP-010 migration comment).
"""

from __future__ import annotations

import datetime
import uuid

import psycopg
from psycopg.rows import DictRow

from app.models import GenerationJob

_COLUMNS = "id, user_id, week_start, status, attempts, last_error"


def claim_or_create_job(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, week_start: datetime.date
) -> GenerationJob:
    row = conn.execute(
        f"""
        insert into generation_jobs (user_id, week_start)
        values (%s, %s)
        on conflict (user_id, week_start) do update set user_id = excluded.user_id
        returning {_COLUMNS}
        """,
        (user_id, week_start),
    ).fetchone()
    assert row is not None
    return GenerationJob.model_validate(row)


def try_start_processing(
    conn: psycopg.Connection[DictRow], job_id: uuid.UUID
) -> GenerationJob | None:
    """MP-033: atomically transitions a job from 'pending' to 'processing'. Returns the updated
    row if this call won the transition, or None if the row was already 'processing', 'done', or
    'failed' — the WHERE clause is the concurrency guarantee: under two near-simultaneous calls for
    the same job_id, Postgres serializes the two UPDATEs on the row, so at most one can match
    status = 'pending' and return a row. Callers must only proceed to call the model when this
    returns non-None.
    """
    row = conn.execute(
        f"""
        update generation_jobs
        set status = 'processing'
        where id = %s and status = 'pending'
        returning {_COLUMNS}
        """,
        (job_id,),
    ).fetchone()
    return GenerationJob.model_validate(row) if row else None


def try_restart_processing(
    conn: psycopg.Connection[DictRow], job_id: uuid.UUID
) -> GenerationJob | None:
    """Atomically reopens a completed/failed week for an explicit remaining-week regenerate."""
    row = conn.execute(
        f"""
        update generation_jobs
        set status = 'processing', last_error = null
        where id = %s and status in ('done', 'failed')
        returning {_COLUMNS}
        """,
        (job_id,),
    ).fetchone()
    return GenerationJob.model_validate(row) if row else None


def try_retry_failed(conn: psycopg.Connection[DictRow], job_id: uuid.UUID) -> GenerationJob | None:
    """Atomically reclaims a failed scheduled job without reopening completed work."""
    row = conn.execute(
        f"""
        update generation_jobs
        set status = 'processing', last_error = null
        where id = %s and status = 'failed'
        returning {_COLUMNS}
        """,
        (job_id,),
    ).fetchone()
    return GenerationJob.model_validate(row) if row else None


def get_job(conn: psycopg.Connection[DictRow], job_id: uuid.UUID) -> GenerationJob | None:
    row = conn.execute(
        f"select {_COLUMNS} from generation_jobs where id = %s", (job_id,)
    ).fetchone()
    return GenerationJob.model_validate(row) if row else None


def update_job_status(
    conn: psycopg.Connection[DictRow],
    job_id: uuid.UUID,
    status: str,
    *,
    last_error: str | None = None,
    increment_attempt: bool = False,
) -> GenerationJob:
    row = conn.execute(
        f"""
        update generation_jobs
        set status = %s, last_error = %s, attempts = attempts + %s
        where id = %s
        returning {_COLUMNS}
        """,
        (status, last_error, 1 if increment_attempt else 0, job_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"generation_jobs row {job_id} not found")
    return GenerationJob.model_validate(row)
