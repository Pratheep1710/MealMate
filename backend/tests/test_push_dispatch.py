"""MP-070: Expo push send — no real network calls, app.services.push_dispatch's httpx.post is
monkeypatched per test rather than hitting the real Expo API.
"""

from __future__ import annotations

import httpx
import pytest

from app.services import push_dispatch


def _fake_post_returning(handler):
    def fake_post(url, *, json=None, headers=None, timeout=None):
        request = httpx.Request("POST", url, json=json, headers=headers)
        return handler(request)

    return fake_post


def test_send_expo_push_returns_the_ticket_id(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers  # no access_token supplied
        return httpx.Response(
            200, json={"data": {"status": "ok", "id": "ticket-abc"}}, request=request
        )

    monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

    ticket_id = push_dispatch.send_expo_push("ExponentPushToken[x]", "Title", "Body", None)

    assert ticket_id == "ticket-abc"


def test_send_expo_push_includes_bearer_token_when_configured(monkeypatch):
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(
            200, json={"data": {"status": "ok", "id": "ticket-1"}}, request=request
        )

    monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

    push_dispatch.send_expo_push("ExponentPushToken[x]", "Title", "Body", "secret-access-token")

    assert seen_headers.get("authorization") == "Bearer secret-access-token"


def test_send_expo_push_raises_on_error_ticket(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"status": "error", "message": "DeviceNotRegistered"}},
            request=request,
        )

    monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

    with pytest.raises(push_dispatch.PushSendError, match="DeviceNotRegistered"):
        push_dispatch.send_expo_push("ExponentPushToken[x]", "Title", "Body", None)


def test_send_expo_push_raises_on_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"}, request=request)

    monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

    with pytest.raises(httpx.HTTPStatusError):
        push_dispatch.send_expo_push("ExponentPushToken[x]", "Title", "Body", None)
