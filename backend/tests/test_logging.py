"""MP-030: structured logging, correlation context, and the redaction wrapper."""

from __future__ import annotations

import json
import logging

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
    payload = {"user_context": {"profile": {"email": "user@example.com"}}}
    scrubbed = redact(payload)
    assert scrubbed["user_context"]["profile"]["email"] == "[REDACTED]"


def test_redact_truncates_long_unnamed_strings_without_full_leak():
    long_prompt = "x" * 1000
    scrubbed = redact({"messages": long_prompt})
    assert "x" * 1000 not in json.dumps(scrubbed)
    assert scrubbed["messages"].startswith("x" * 500)
    assert "truncated" in scrubbed["messages"]


def test_redact_fully_scrubs_prompt_keyed_values_regardless_of_length():
    scrubbed = redact({"prompt": "short but still a prompt"})
    assert scrubbed["prompt"] == "[REDACTED]"


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
