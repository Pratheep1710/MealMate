"""Idempotently provisions Supabase Auth test users needed for the *live* integration tests that
otherwise skip in CI: MP-012's single sign-in test (backend/tests/test_supabase_auth.py) and
MP-023's cross-user RLS denial test (mobile/src/lib/__tests__/rls-cross-user.test.ts), which needs
TWO confirmed users. This replaces the one-off Admin API call MP-012's user was originally created
with (undocumented, not reproducible) with a script anyone with the service_role key can re-run.

Usage:
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \\
        python backend/scripts/provision_ci_test_users.py

Creates (or finds, if already present) two confirmed users — ci-test-user@mealmate.test and
ci-test-user-b@mealmate.test — each with a random password, and seeds a minimal user_profiles row
for both (service_role bypasses RLS, so this can write directly). Prints the four
SUPABASE_TEST_USER*_EMAIL/PASSWORD values to set as GitHub repo secrets, alongside the existing
SUPABASE_TEST_USER_EMAIL/PASSWORD from MP-012 and SUPABASE_TEST_USER_B_EMAIL/PASSWORD for MP-023 —
see docs/MP-023-cross-user-rls-test.md for where these get wired into CI.

Never commit the printed passwords anywhere — copy them straight into GitHub repo secrets and
discard.
"""

from __future__ import annotations

import os
import secrets
import sys

import httpx

_USERS = [
    ("ci-test-user@mealmate.test", "SUPABASE_TEST_USER"),
    ("ci-test-user-b@mealmate.test", "SUPABASE_TEST_USER_B"),
]


def _check(response: httpx.Response) -> httpx.Response:
    """raise_for_status(), but with the response body attached — the default exception message
    is just the status line, which isn't enough to diagnose *why* a 422 happened.
    """
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"{exc}\nResponse body: {response.text}") from exc
    return response


def _find_user_id_by_email(client: httpx.Client, email: str) -> str | None:
    """Scans the (paginated) full admin user list for a case-insensitive email match. Doesn't rely
    on /admin/users supporting a `filter` query param — that isn't reliably supported across
    GoTrue versions, and silently returning zero results on an unsupported filter is exactly what
    caused this function to exist (see _find_or_create_user).
    """
    page = 1
    while True:
        response = _check(
            client.get("/auth/v1/admin/users", params={"page": page, "per_page": 200})
        )
        users = response.json().get("users", [])
        if not users:
            return None
        for user in users:
            if user.get("email", "").lower() == email.lower():
                return user["id"]
        page += 1


def _find_or_create_user(client: httpx.Client, email: str) -> tuple[str, str]:
    """Returns (user_id, password). If the user already exists, its password is NOT known (Admin
    API never returns it) — this only re-provisions the password on first creation. Re-running
    this script for an already-provisioned user prints its id but a fresh random password that
    does NOT match what's already set; delete the user in the dashboard first if you need to
    rotate its password via this script.

    Tries to create first rather than pre-checking existence: GoTrue rejects a duplicate email
    with 422, which is the reliable signal to fall back to looking the user up, instead of
    depending on /admin/users' filtering support (see _find_user_id_by_email's docstring).
    """
    password = secrets.token_urlsafe(24)
    response = client.post(
        "/auth/v1/admin/users",
        json={"email": email, "password": password, "email_confirm": True},
    )
    if response.status_code == 422:
        existing_id = _find_user_id_by_email(client, email)
        if existing_id is not None:
            return existing_id, "(already provisioned — password unknown, see script docstring)"
        raise RuntimeError(
            f"Creating {email} failed (422) and no existing user with that email was found — "
            f"this is a real validation error, not a duplicate. Response body: {response.text}"
        )
    _check(response)
    return response.json()["id"], password


def _seed_profile(client: httpx.Client, user_id: str) -> None:
    _check(
        client.post(
            "/rest/v1/user_profiles",
            json={"id": user_id, "dietary_restrictions": [], "grocery_day": "monday"},
            headers={"Prefer": "resolution=ignore-duplicates"},
        )
    )


def main() -> int:
    # .strip() guards against a stray trailing newline/whitespace from copy-pasting a long key
    # into a terminal (e.g. PowerShell splitting a paste across lines) — that would otherwise
    # surface as an opaque "Illegal header value" exception deep in httpx instead of a clear error.
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    service_role_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not service_role_key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.", file=sys.stderr)
        return 1

    with httpx.Client(
        base_url=url,
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        },
        timeout=15,
    ) as client:
        print("Set these as GitHub repo secrets (Settings -> Secrets and variables -> Actions):\n")
        for email, prefix in _USERS:
            user_id, password = _find_or_create_user(client, email)
            _seed_profile(client, user_id)
            print(f"{prefix}_EMAIL={email}")
            print(f"{prefix}_PASSWORD={password}")
            print(f"  (user id: {user_id})\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
