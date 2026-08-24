"""MP-030: structured logging, correlation context, and the redaction wrapper."""

from __future__ import annotations

import dataclasses
import datetime
import json
import logging
import uuid

from pydantic import BaseModel

from app.logging import correlation_context, get_logger, redact


def test_redact_scrubs_sensitively_named_keys():
    payload = {
        "openai_api_key": "sk-real-secret",
        "user_email": "user@example.com",
        "supabase_service_role_key": "service-secret",
        "safe_field": "keep me",
    }
    scrubbed = redact(payload)
    assert scrubbed["openai_api_key"] == "[REDACTED]"
    assert scrubbed["user_email"] == "[REDACTED]"
    assert scrubbed["supabase_service_role_key"] == "[REDACTED]"
    assert scrubbed["safe_field"] == "keep me"


def test_redact_scrubs_nested_structures():
    # Outer key deliberately doesn't match a sensitive marker itself, so this actually exercises
    # recursion into a nested dict rather than short-circuiting on the outer key name.
    payload = {"profile_data": {"profile": {"email": "user@example.com"}}}
    scrubbed = redact(payload)
    assert scrubbed["profile_data"]["profile"]["email"] == "[REDACTED]"


def test_redact_truncates_long_unnamed_strings_without_full_leak():
    # Key deliberately doesn't match a sensitive marker, to exercise the length-based truncation
    # backstop rather than the (now broader) key-name redaction.
    long_prompt = "x" * 1000
    scrubbed = redact({"raw_dump": long_prompt})
    assert "x" * 1000 not in json.dumps(scrubbed)
    assert scrubbed["raw_dump"].startswith("x" * 500)
    assert "truncated" in scrubbed["raw_dump"]


def test_redact_fully_scrubs_prompt_keyed_values_regardless_of_length():
    scrubbed = redact({"prompt": "short but still a prompt"})
    assert scrubbed["prompt"] == "[REDACTED]"


def test_redact_fully_scrubs_short_content_under_generic_payload_keys():
    """Regression: a short prompt/context string under a generic key like "messages" or
    "content" used to slip through unredacted — only sensitively-named keys or strings over 500
    chars were scrubbed, so a real (short) LLM prompt or user-context blurb would be logged
    verbatim. These key names are now in _SENSITIVE_KEY_MARKERS, so length no longer matters.
    """
    scrubbed = redact(
        {
            "messages": "What's for dinner, I'm vegan and allergic to nuts",
            "content": "short content",
            "context": "short context",
        }
    )
    assert scrubbed["messages"] == "[REDACTED]"
    assert scrubbed["content"] == "[REDACTED]"
    assert scrubbed["context"] == "[REDACTED]"


def test_redact_normalizes_and_scrubs_pydantic_models():
    """Regression: a pydantic model (e.g. a raw OpenAI request/user-context object) previously
    fell through every isinstance check and was returned as-is, reaching json.dumps(...,
    default=str) unscrubbed — leaking its full str() representation, secrets included.
    """

    class UserContext(BaseModel):
        email: str
        dietary_restrictions: list[str]

    user_context = UserContext(email="user@example.com", dietary_restrictions=["nuts"])
    scrubbed = redact({"user": user_context})
    assert scrubbed["user"]["email"] == "[REDACTED]"
    assert scrubbed["user"]["dietary_restrictions"] == ["nuts"]


def test_redact_normalizes_and_scrubs_dataclasses():
    @dataclasses.dataclass
    class PromptPayload:
        prompt: str
        job_id: str

    # Outer key deliberately doesn't match a sensitive marker, so this exercises the
    # dataclasses.asdict() normalization path rather than short-circuiting on the outer key name.
    scrubbed = redact({"obj": PromptPayload(prompt="secret prompt text", job_id="job-1")})
    assert scrubbed["obj"]["prompt"] == "[REDACTED]"
    assert scrubbed["obj"]["job_id"] == "job-1"


def test_redact_replaces_unknown_object_types_with_redacted_marker():
    """Regression: any object that isn't a Mapping/list/str/known-safe-scalar/pydantic
    model/dataclass previously passed through unchanged and was serialized wholesale by
    json.dumps(..., default=str) — the exact "reach a log sink unscrubbed" failure mode the
    Phase 2 brief calls out. Unknown-shaped objects are now redacted outright.
    """

    class OpaqueThing:
        def __str__(self) -> str:
            return "raw-secret-payload-inside-str"

    scrubbed = redact({"thing": OpaqueThing()})
    assert scrubbed["thing"] == "[REDACTED]"
    assert "raw-secret-payload-inside-str" not in json.dumps(scrubbed, default=str)


def test_redact_keeps_safe_scalar_types_as_is():
    """Correlation/structural values (ids, dates) must survive redact() unchanged — the strict
    unknown-object fallback must not also start redacting the harmless values callers legitimately
    need to log."""
    job_id = uuid.uuid4()
    today = datetime.date(2026, 8, 23)
    scrubbed = redact({"job_id": job_id, "count": 3, "rate": 0.5, "active": True, "note": None})
    assert scrubbed["job_id"] == job_id
    assert scrubbed["count"] == 3
    assert scrubbed["rate"] == 0.5
    assert scrubbed["active"] is True
    assert scrubbed["note"] is None
    assert redact(today) == today


def test_bound_logger_emits_valid_json_with_correlation_context(caplog):
    logger = get_logger("test_logging")
    with (
        caplog.at_level(logging.INFO, logger="app.test_logging"),
        correlation_context(job_id="job-1", user_id="user-1", week_start="2026-08-24"),
    ):
        logger.info("job.started", extra_field="value")

    assert len(caplog.records) == 1
    record = json.loads(caplog.records[0].getMessage())
    assert record["event"] == "job.started"
    assert record["job_id"] == "job-1"
    assert record["user_id"] == "user-1"
    assert record["week_start"] == "2026-08-24"
    assert record["extra_field"] == "value"
    assert record["level"] == "info"
    assert "timestamp" in record


def test_bound_logger_never_leaks_secret_field_values(caplog):
    logger = get_logger("test_logging")
    with caplog.at_level(logging.INFO, logger="app.test_logging"):
        logger.info("openai.call", api_key="sk-should-never-appear", prompt="also secret")

    message = caplog.records[0].getMessage()
    assert "sk-should-never-appear" not in message
    assert "also secret" not in message


def test_correlation_context_resets_after_block(caplog):
    logger = get_logger("test_logging")
    with caplog.at_level(logging.INFO, logger="app.test_logging"):
        with correlation_context(job_id="job-1"):
            logger.info("inside")
        logger.info("outside")

    inside = json.loads(caplog.records[0].getMessage())
    outside = json.loads(caplog.records[1].getMessage())
    assert inside["job_id"] == "job-1"
    assert "job_id" not in outside


def test_nested_correlation_context_overrides_only_given_fields(caplog):
    logger = get_logger("test_logging")
    with (
        caplog.at_level(logging.INFO, logger="app.test_logging"),
        correlation_context(job_id="job-1", user_id="user-1"),
        correlation_context(week_start="2026-08-24"),
    ):
        logger.info("nested")

    record = json.loads(caplog.records[0].getMessage())
    assert record["job_id"] == "job-1"
    assert record["user_id"] == "user-1"
    assert record["week_start"] == "2026-08-24"
