from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from generation_test_helpers import WEEK_START, make_context, menu_for_context

from app.models import GenerationJob
from app.services import generation_engine
from app.services.openai_generation import GenerationProviderError


class _Connection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _SequenceGenerator:
    def __init__(self, outputs) -> None:
        self.outputs = list(outputs)
        self.messages = []

    def generate(self, messages):
        self.messages.append(messages)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output


def _job(*, status: str = "processing", attempts: int = 0) -> GenerationJob:
    return GenerationJob(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        week_start=WEEK_START,
        status=status,
        attempts=attempts,
        last_error=None,
    )


def _wire(monkeypatch: pytest.MonkeyPatch, context, job: GenerationJob):
    updates = []
    monkeypatch.setattr(generation_engine, "_claim", lambda *args: job)
    monkeypatch.setattr(
        generation_engine,
        "build_generation_context",
        lambda *args, **kwargs: context,
    )

    def update(conn, job_id, status, **kwargs):
        updates.append((status, kwargs))
        return job.model_copy(
            update={
                "status": status,
                "attempts": job.attempts
                + sum(
                    1
                    for update_status, update_kwargs in updates
                    if update_status == "processing" and update_kwargs.get("increment_attempt")
                ),
                "last_error": kwargs.get("last_error"),
            }
        )

    persistence = SimpleNamespace(
        snapshot=SimpleNamespace(), notification=SimpleNamespace(id=uuid.uuid4())
    )
    monkeypatch.setattr(generation_engine.jobs_repo, "update_job_status", update)
    monkeypatch.setattr(generation_engine, "persist_generated_plan", lambda *args: persistence)
    return updates


def test_invalid_first_output_is_retried_with_feedback_then_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context()
    job = _job()
    updates = _wire(monkeypatch, context, job)
    generator = _SequenceGenerator(
        [menu_for_context(context, include_nonveg=False), menu_for_context(context)]
    )
    conn = _Connection()

    outcome = generation_engine.run_generation_engine(  # type: ignore[arg-type]
        conn, job.user_id, WEEK_START, generator
    )

    assert outcome is not None
    assert outcome.plan.source == "openai"
    assert len(generator.messages) == 2
    assert len(generator.messages[1]) == 3  # retry feedback follows static + dynamic context
    assert [status for status, _ in updates] == ["processing", "processing", "done"]


def test_two_provider_failures_use_fallback_and_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context()
    job = _job()
    updates = _wire(monkeypatch, context, job)
    generator = _SequenceGenerator(
        [GenerationProviderError("timeout"), GenerationProviderError("timeout")]
    )

    outcome = generation_engine.run_generation_engine(  # type: ignore[arg-type]
        _Connection(), job.user_id, WEEK_START, generator
    )

    assert outcome is not None
    assert outcome.plan.source == "fallback"
    assert outcome.job.status == "done"
    assert updates[-1][1]["last_error"].startswith("fallback")


def test_existing_claim_returns_without_calling_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generation_engine, "_claim", lambda *args: None)
    generator = _SequenceGenerator([])

    outcome = generation_engine.run_generation_engine(  # type: ignore[arg-type]
        _Connection(), uuid.uuid4(), WEEK_START, generator
    )

    assert outcome is None
    assert generator.messages == []


def test_claim_failure_rolls_back_before_propagating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generation_engine,
        "_claim",
        lambda *args: (_ for _ in ()).throw(RuntimeError("claim failed")),
    )
    conn = _Connection()

    with pytest.raises(RuntimeError, match="claim failed"):
        generation_engine.run_generation_engine(  # type: ignore[arg-type]
            conn, uuid.uuid4(), WEEK_START, _SequenceGenerator([])
        )

    assert conn.rollbacks == 1
    assert conn.commits == 0


def test_scheduled_claim_atomically_retries_a_failed_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = _job(status="failed")
    retried = failed.model_copy(update={"status": "processing"})
    monkeypatch.setattr(generation_engine, "claim_job", lambda *args: None)
    monkeypatch.setattr(generation_engine.jobs_repo, "claim_or_create_job", lambda *args: failed)
    monkeypatch.setattr(generation_engine.jobs_repo, "try_retry_failed", lambda *args: retried)

    claimed = generation_engine._claim(  # type: ignore[arg-type]
        _Connection(), failed.user_id, WEEK_START, None
    )

    assert claimed == retried


def test_persistence_failure_marks_job_failed_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_context()
    job = _job()
    updates = _wire(monkeypatch, context, job)
    monkeypatch.setattr(
        generation_engine,
        "persist_generated_plan",
        lambda *args: (_ for _ in ()).throw(RuntimeError("write failed")),
    )
    conn = _Connection()

    with pytest.raises(RuntimeError, match="write failed"):
        generation_engine.run_generation_engine(  # type: ignore[arg-type]
            conn, job.user_id, WEEK_START, _SequenceGenerator([menu_for_context(context)])
        )

    assert conn.rollbacks == 1
    assert updates[-1][0] == "failed"
