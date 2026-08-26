"""MP-070: the actual Expo push send — the piece app/jobs/entrypoints.py's
run_daily_reminder_dispatch docstring calls out as "M6 scope", i.e. this phase. Kept minimal per
docs/MP-001's non-goals ("no circuit breaker / backoff-jitter tuning"): one HTTP call, the caller
decides whether to retry.
"""

from __future__ import annotations

import httpx

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class PushSendError(Exception):
    """Raised when Expo's push API rejects the request or a ticket comes back with an error."""


def send_expo_push(
    token: str, title: str, body: str, access_token: str | None, *, timeout: float = 10.0
) -> str:
    """Sends one push via Expo's HTTP API and returns the ticket id.

    `access_token` is only required if the Expo project has "Enhanced Push Notification Security"
    turned on (app/config.py's ExpoConfig — optional, not one of the fail-fast required fields);
    omitted from the request entirely when absent rather than sent as a blank header.
    """
    headers = {"accept": "application/json", "content-type": "application/json"}
    if access_token:
        headers["authorization"] = f"Bearer {access_token}"

    response = httpx.post(
        _EXPO_PUSH_URL,
        json={"to": token, "title": title, "body": body},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    ticket = payload.get("data")
    if not ticket or ticket.get("status") != "ok":
        error = (ticket or {}).get("message", "unknown error")
        raise PushSendError(f"Expo push rejected: {error}")
    return str(ticket["id"])
