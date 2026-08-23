"""MP-012: sign-in / JWT-scope integration test.

Requires a live Supabase project (MP-006) with a real test user provisioned in Supabase Auth —
neither exists in this repo, so the test SKIPS (not fails, not errors) whenever the required
env vars aren't set, rather than blocking the rest of the suite. Once you've created the project
and a test user, set the four env vars below (e.g. in backend/.env) and this test becomes a real
assertion that sign-in works and the returned JWT is correctly scoped to that user.

Setup, once you have a Supabase project:
  1. Dashboard → Authentication → Users → Add user (email + password), confirmed.
  2. Dashboard → Project Settings → API → copy Project URL and anon public key.
  3. Set SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_TEST_USER_EMAIL, SUPABASE_TEST_USER_PASSWORD.
"""

import os
import uuid

import httpx
import jwt
import pytest

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
TEST_EMAIL = os.environ.get("SUPABASE_TEST_USER_EMAIL")
TEST_PASSWORD = os.environ.get("SUPABASE_TEST_USER_PASSWORD")

pytestmark = pytest.mark.skipif(
    not all([SUPABASE_URL, SUPABASE_ANON_KEY, TEST_EMAIL, TEST_PASSWORD]),
    reason=(
        "No live Supabase project configured yet (MP-006 not done). Set SUPABASE_URL, "
        "SUPABASE_ANON_KEY, SUPABASE_TEST_USER_EMAIL, SUPABASE_TEST_USER_PASSWORD to run this "
        "against a real project."
    ),
)


def test_password_sign_in_returns_a_correctly_scoped_jwt():
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=10,
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert "access_token" in body
    assert body.get("token_type") == "bearer"

    # Structural decode only — this test's job is to confirm sign-in works and the token carries
    # the right claims, not to re-verify Supabase's own signing. Claim-format checks below are
    # exactly what backend/app/config.py's consumers (MP-013 RLS, FastAPI JWT dependency, per
    # technical spec §3) rely on.
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims.get("role") == "authenticated"
    assert uuid.UUID(claims["sub"])  # sub must be a valid user id
    assert claims.get("email") == TEST_EMAIL
