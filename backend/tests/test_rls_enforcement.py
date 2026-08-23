"""MP-031: proves RLS itself (not just Python-side WHERE-clause scoping) rejects cross-user
access when repository functions run over an `authenticated`-role connection with
`request.jwt.claim.sub` set — the same mechanism supabase/tests/rls.test.mjs and
mobile/src/lib/__tests__/rls-cross-user.test.ts exercise from the client path, applied here to the
backend's own repository layer per test_repositories.py's TestProfilesRepository etc., which all
connect as the elevated/service_role-equivalent role and so cannot catch an RLS regression on
their own.
"""

from __future__ import annotations

import datetime

from app.repositories import plans as plans_repo
from app.repositories import profiles as profiles_repo


class TestProfilesRLS:
    def test_authenticated_user_cannot_read_another_users_profile(
        self, conn, make_user, as_authenticated_user
    ):
        user_a = make_user()
        user_b = make_user()

        as_authenticated_user(user_b)

        # Called with user_a's id directly (not scoped to "own" id) — if RLS were misconfigured
        # or absent, this would leak user A's row instead of coming back empty.
        assert profiles_repo.get_profile(conn, user_a) is None

    def test_authenticated_user_can_read_own_profile(self, conn, make_user, as_authenticated_user):
        user_a = make_user()

        as_authenticated_user(user_a)

        fetched = profiles_repo.get_profile(conn, user_a)
        assert fetched is not None
        assert fetched.id == user_a


class TestMealPlansRLS:
    def test_authenticated_user_cannot_read_another_users_week_plan(
        self, conn, make_user, as_authenticated_user
    ):
        user_a = make_user()
        user_b = make_user()
        week_start = datetime.date(2026, 8, 24)
        plans_repo.create_plan_day(conn, user_a, week_start, "morning")

        as_authenticated_user(user_b)

        assert plans_repo.get_week_plan(conn, user_a, week_start) == []

    def test_authenticated_user_can_read_own_week_plan(
        self, conn, make_user, as_authenticated_user
    ):
        user_a = make_user()
        week_start = datetime.date(2026, 8, 24)
        created = plans_repo.create_plan_day(conn, user_a, week_start, "morning")

        as_authenticated_user(user_a)

        week_plan = plans_repo.get_week_plan(conn, user_a, week_start)
        assert [p.id for p in week_plan] == [created.id]
