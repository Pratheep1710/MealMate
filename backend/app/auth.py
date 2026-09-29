"""Phase 9 (MP-092/093/094): verifies the mobile client's Supabase access token for the live
FastAPI endpoints (app/main.py). The mobile client authenticates with Supabase directly
(supabase-js) and sends the resulting access token as a bearer header — this module is the one
place that token gets decoded and turned into a trusted user id, mirroring exactly the claim
shape backend/tests/test_supabase_auth.py already asserts on (`role == "authenticated"`,
`sub` a UUID) — that test's own comment names this "FastAPI JWT dependency" as the anticipated
consumer.
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, Header, HTTPException

from app.config import AppConfig
from app.deps import get_config

_ALGORITHM = "HS256"
_AUDIENCE = "authenticated"


def get_current_user_id(
    authorization: str | None = Header(default=None),
    config: AppConfig = Depends(get_config),
) -> uuid.UUID:
    """Raises HTTPException(401) on any missing/malformed/invalid/expired token, and
    HTTPException(500) if this deployment has no SUPABASE_JWT_SECRET configured — a
    misconfiguration, not something the caller can fix by retrying.
    """
    if config.supabase.jwt_secret is None:
        raise HTTPException(status_code=500, detail="SUPABASE_JWT_SECRET is not configured")

    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    try:
        claims = jwt.decode(
            token, config.supabase.jwt_secret, algorithms=[_ALGORITHM], audience=_AUDIENCE
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc

    try:
        return uuid.UUID(claims["sub"])
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="token has no valid sub claim") from exc
