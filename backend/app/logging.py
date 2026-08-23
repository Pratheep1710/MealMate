"""MP-030: structured logging with correlation context and a redaction wrapper.

Every event logged through get_logger() is emitted as one JSON line carrying whatever
job/user/week correlation context is currently bound (see correlation_context()), and every field
value — context and per-call alike — passes through redact() first. That makes this module the
single choke point MP-040 (the OpenAI call, next phase) will log through by default: raw
prompt/user-context payloads can't reach a log sink unscrubbed, because there's no logging path
here that skips redact().
"""

from __future__ import annotations

import contextvars
import datetime
import json
import logging
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, TextIO

# Key-name substrings that force full redaction regardless of value. Deliberately broad — a
# false-positive redaction (a harmless field named "token_count" getting scrubbed) is cheap;
# a missed secret or a leaked prompt/PII field is not.
_SENSITIVE_KEY_MARKERS: Sequence[str] = (
    "key",
    "token",
    "secret",
    "password",
    "authorization",
    "jwt",
    "prompt",
    "email",
    "phone",
)

# Anything else long gets truncated rather than redacted outright — this is the backstop for
# fields that aren't sensitively *named* but could still carry a full LLM prompt or a serialized
# user-context blob (e.g. "messages", "context") if logged carelessly.
_MAX_STRING_LEN = 500
_REDACTED = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)


def redact(value: Any, *, key: str = "") -> Any:
    """Recursively scrubs `value`. Call with the field name as `key` for top-level calls so
    sensitively-named fields (see _SENSITIVE_KEY_MARKERS) are fully redacted; nested dict/list
    values are walked with their own keys.
    """
    if _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, Mapping):
        return {str(k): redact(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, key=key) for v in value]
    if isinstance(value, str) and len(value) > _MAX_STRING_LEN:
        omitted = len(value) - _MAX_STRING_LEN
        return f"{value[:_MAX_STRING_LEN]}...[truncated {omitted} chars]"
    return value


_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)
_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)
_week_start: contextvars.ContextVar[str | None] = contextvars.ContextVar("week_start", default=None)
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

_CONTEXT_VARS: Mapping[str, contextvars.ContextVar[str | None]] = {
    "job_id": _job_id,
    "user_id": _user_id,
    "week_start": _week_start,
    "correlation_id": _correlation_id,
}


@contextmanager
def correlation_context(
    *,
    job_id: str | None = None,
    user_id: str | None = None,
    week_start: str | None = None,
    correlation_id: str | None = None,
) -> Iterator[None]:
    """Binds correlation fields for the duration of the `with` block (nestable — an inner block's
    fields override the outer's; unset fields keep whatever the outer block bound). Every
    get_logger().info/warning/error() call issued inside picks these up automatically.
    """
    values = {
        "job_id": job_id,
        "user_id": user_id,
        "week_start": week_start,
        "correlation_id": correlation_id,
    }
    tokens = [
        (_CONTEXT_VARS[name], _CONTEXT_VARS[name].set(value))
        for name, value in values.items()
        if value is not None
    ]
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def _current_context() -> dict[str, str]:
    return {name: value for name, var in _CONTEXT_VARS.items() if (value := var.get()) is not None}


class _JsonLineHandler(logging.StreamHandler[TextIO]):
    def format(self, record: logging.LogRecord) -> str:
        # The record's message is already a fully-formed JSON string (built in BoundLogger below)
        # — this handler exists only to send it to stdout as one line, not to re-format it.
        return record.getMessage()


class BoundLogger:
    """Thin wrapper around a stdlib logging.Logger that always emits structured, redacted JSON."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _emit(self, level: int, event: str, fields: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "level": logging.getLevelName(level).lower(),
            "event": event,
            **_current_context(),
            **redact(fields),
        }
        self._logger.log(level, json.dumps(record, default=str))

    def debug(self, event: str, **fields: Any) -> None:
        self._emit(logging.DEBUG, event, fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, fields)


_configured = False


def _configure_root_once() -> None:
    global _configured
    if _configured:
        return
    handler = _JsonLineHandler(stream=sys.stdout)
    root = logging.getLogger("app")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Deliberately left propagating (the stdlib default) rather than set to False: pytest's
    # caplog, and any other tooling that captures via the root logger, relies on propagation to
    # see these records. Nothing configures a root handler in this app, so there's no duplicate
    # output in practice.
    _configured = True


def get_logger(name: str) -> BoundLogger:
    _configure_root_once()
    return BoundLogger(logging.getLogger(f"app.{name}"))
