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


class TestSendWithOneRetry:
    """MP-072: exactly one same-evening retry — the AC is specifically that a second consecutive
    failure never triggers a third attempt, not just that a single failure gets retried once.
    """

    def test_a_first_failure_is_retried_and_the_retry_can_succeed(self, monkeypatch):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(
                    200, json={"data": {"status": "error", "message": "transient"}}, request=request
                )
            return httpx.Response(
                200, json={"data": {"status": "ok", "id": "ticket-2"}}, request=request
            )

        monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

        ticket_id = push_dispatch.send_expo_push_with_one_retry(
            "ExponentPushToken[x]", "Title", "Body", None
        )

        assert ticket_id == "ticket-2"
        assert len(calls) == 2

    def test_two_consecutive_failures_raise_after_exactly_two_attempts_no_third(self, monkeypatch):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(
                200, json={"data": {"status": "error", "message": "still failing"}}, request=request
            )

        monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

        with pytest.raises(push_dispatch.PushSendError, match="still failing"):
            push_dispatch.send_expo_push_with_one_retry(
                "ExponentPushToken[x]", "Title", "Body", None
            )

        assert len(calls) == 2  # the initial attempt + exactly one retry, never a third

    def test_a_transport_error_on_the_retry_also_only_attempts_twice(self, monkeypatch):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(500, json={"error": "boom"}, request=request)
            return httpx.Response(500, json={"error": "boom again"}, request=request)

        monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

        with pytest.raises(httpx.HTTPStatusError):
            push_dispatch.send_expo_push_with_one_retry(
                "ExponentPushToken[x]", "Title", "Body", None
            )

        assert len(calls) == 2

    def test_a_successful_first_attempt_never_retries(self, monkeypatch):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(
                200, json={"data": {"status": "ok", "id": "ticket-1"}}, request=request
            )

        monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

        ticket_id = push_dispatch.send_expo_push_with_one_retry(
            "ExponentPushToken[x]", "Title", "Body", None
        )

        assert ticket_id == "ticket-1"
        assert len(calls) == 1


class TestGetExpoReceipts:
    def test_returns_the_raw_data_mapping(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "POST"
            import json as _json

            assert _json.loads(request.content) == {"ids": ["ticket-1", "ticket-2"]}
            return httpx.Response(
                200,
                json={
                    "data": {
                        "ticket-1": {"status": "ok"},
                        "ticket-2": {
                            "status": "error",
                            "message": "not registered",
                            "details": {"error": "DeviceNotRegistered"},
                        },
                    }
                },
                request=request,
            )

        monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

        receipts = push_dispatch.get_expo_receipts(["ticket-1", "ticket-2"], None)

        assert receipts["ticket-1"]["status"] == "ok"
        assert receipts["ticket-2"]["status"] == "error"

    def test_an_empty_ticket_list_makes_no_request(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("should not be called for an empty ticket list")

        monkeypatch.setattr(push_dispatch.httpx, "post", _fake_post_returning(handler))

        assert push_dispatch.get_expo_receipts([], None) == {}
