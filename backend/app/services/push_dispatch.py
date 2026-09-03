"""MP-070/072/073: the Expo push send, the one-same-evening-retry wrapper around it, and the
receipt-reconciliation lookup. Kept minimal per docs/MP-001's non-goals ("no circuit breaker /
backoff-jitter tuning"): a single bounded retry, no exponential backoff, no jitter.
"""

from __future__ import annotations

import httpx

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"


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


def send_expo_push_with_one_retry(
    token: str, title: str, body: str, access_token: str | None, *, timeout: float = 10.0
) -> str:
    """MP-072: "Retry once, same evening" (technical spec §2.2) as a single immediate retry of
    *this one send* — not a scheduling concept, not a second script run. Tries once; on a rejected
    ticket or transport error, tries exactly once more; a second failure propagates to the caller,
    which is what actually happened after the one retry the v1 policy allows. No backoff/jitter
    (docs/MP-001 non-goal) — the failure modes this covers (a single dropped connection, a
    transient Expo 5xx) don't need one, and the whole call is already inside a ~10s timeout twice
    over at worst.
    """
    try:
        return send_expo_push(token, title, body, access_token, timeout=timeout)
    except (PushSendError, httpx.HTTPError):
        return send_expo_push(token, title, body, access_token, timeout=timeout)


def get_expo_receipts(
    ticket_ids: list[str], access_token: str | None, *, timeout: float = 10.0
) -> dict[str, dict[str, object]]:
    """MP-073: looks up delivery receipts for previously-sent ticket ids via Expo's separate
    getReceipts endpoint (the send call only confirms Expo *accepted* the push for delivery, not
    that it reached the device — the receipt is the actual delivery outcome, available ~some time
    after the send, hence the ~30-minute-later follow-up job this feeds). Returns Expo's raw
    `data` mapping (ticket id -> `{"status": "ok"}` or `{"status": "error", "message": ...,
    "details": {"error": ...}}`) unfiltered — the caller decides what each status means for
    `notification_log`.
    """
    if not ticket_ids:
        return {}
    headers = {"accept": "application/json", "content-type": "application/json"}
    if access_token:
        headers["authorization"] = f"Bearer {access_token}"

    response = httpx.post(
        _EXPO_RECEIPTS_URL,
        json={"ids": ticket_ids},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data")
    return dict(data) if isinstance(data, dict) else {}
