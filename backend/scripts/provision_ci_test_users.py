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


def _find_or_create_user(client: httpx.Client, email: str) -> tuple[str, str]:
    """Returns (user_id, password). If the user already exists, its password is NOT known (Admin
    API never returns it) — this only re-provisions the password on first creation. Re-running
    this script for an already-provisioned user prints its id but a fresh random password that
    does NOT match what's already set; delete the user in the dashboard first if you need to
    rotate its password via this script.
    """
    existing = client.get("/auth/v1/admin/users", params={"filter": f"email.eq.{email}"})
    existing.raise_for_status()
    users = existing.json().get("users", [])
    if users:
        return users[0]["id"], "(already provisioned — password unknown, see script docstring)"

    password = secrets.token_urlsafe(24)
    response = client.post(
        "/auth/v1/admin/users",
        json={"email": email, "password": password, "email_confirm": True},
    )
    response.raise_for_status()
    return response.json()["id"], password


def _seed_profile(client: httpx.Client, user_id: str) -> None:
    client.post(
        "/rest/v1/user_profiles",
        json={"id": user_id, "dietary_restrictions": [], "grocery_day": "monday"},
        headers={"Prefer": "resolution=ignore-duplicates"},
    ).raise_for_status()


def main() -> int:
    url = os.environ.get("SUPABASE_URL")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
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
