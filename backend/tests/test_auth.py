"""Phase 9: app/auth.py's JWT verification — pure unit tests, no DB or live Supabase needed.

Mirrors the exact claim shape test_supabase_auth.py already asserts a real Supabase sign-in
produces (`role: "authenticated"`, `sub: <uuid>`) — this is the anticipated consumer that test's
own comment names.
"""

from __future__ import annotations

import uuid

import jwt
import pytest
from fastapi import HTTPException

from app.auth import get_current_user_id
from app.config import AppConfig, ExpoConfig, OpenAIConfig, RenderConfig, SupabaseConfig

_SECRET = "test-jwt-secret-that-is-long-enough-for-hs256"
_USER_ID = uuid.uuid4()


def _config(*, jwt_secret: str | None = _SECRET) -> AppConfig:
    return AppConfig(
        supabase=SupabaseConfig(
            url="https://example.supabase.co",
            anon_key="anon",
            service_role_key="service",
            db_host="db.example.supabase.co",
            db_password="password",
            jwt_secret=jwt_secret,
        ),
        openai=OpenAIConfig(api_key="sk-test", model="gpt-test"),
        expo=ExpoConfig(),
        render=RenderConfig(),
    )


def _token(*, secret: str = _SECRET, **claim_overrides: object) -> str:
    claims = {"sub": str(_USER_ID), "role": "authenticated", "aud": "authenticated"}
    claims.update(claim_overrides)
    return jwt.encode(claims, secret, algorithm="HS256")


def test_a_correctly_signed_token_resolves_to_its_sub_claim() -> None:
    user_id = get_current_user_id(authorization=f"Bearer {_token()}", config=_config())
    assert user_id == _USER_ID


def test_missing_authorization_header_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(authorization=None, config=_config())
    assert exc_info.value.status_code == 401


def test_a_non_bearer_authorization_header_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(authorization=f"Basic {_token()}", config=_config())
    assert exc_info.value.status_code == 401


def test_a_token_signed_with_the_wrong_secret_is_rejected() -> None:
    bad_token = _token(secret="wrong-secret")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(authorization=f"Bearer {bad_token}", config=_config())
    assert exc_info.value.status_code == 401


def test_a_token_with_the_wrong_audience_is_rejected() -> None:
    bad_token = _token(aud="something-else")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(authorization=f"Bearer {bad_token}", config=_config())
    assert exc_info.value.status_code == 401


def test_an_expired_token_is_rejected() -> None:
    import datetime

    expired = _token(exp=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1))
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(authorization=f"Bearer {expired}", config=_config())
    assert exc_info.value.status_code == 401


def test_a_token_with_a_malformed_sub_claim_is_rejected() -> None:
    bad_token = _token(sub="not-a-uuid")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(authorization=f"Bearer {bad_token}", config=_config())
    assert exc_info.value.status_code == 401


def test_a_deployment_with_no_configured_jwt_secret_fails_with_a_500_not_a_401() -> None:
    # A misconfiguration (this deployment never set SUPABASE_JWT_SECRET) is not the caller's
    # fault — distinguishing it from a bad/missing token (401) matters for anyone debugging this.
    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(authorization=f"Bearer {_token()}", config=_config(jwt_secret=None))
    assert exc_info.value.status_code == 500
