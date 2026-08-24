"""MP-031: session-scoped Postgres fixture for repository integration tests.

Builds a throwaway database from the exact files in supabase/migrations/ — the real schema and
0006's RLS policies, not a hand-rolled test schema — plus a minimal auth-schema stub mirroring
supabase/tests/helpers.mjs (auth.users + auth.uid()), so these tests run against the same schema
the live Supabase project runs, per the Phase 2 brief's "not a bypassed test database" requirement.

Repositories connect the same way app/db.py does in production: as the elevated Postgres role
(the direct-connection equivalent of Supabase's service_role), which bypasses RLS by Postgres
design — appropriate for the job/notification/generation paths that are genuinely
service_role-privileged in production (see supabase/migrations/0006's comments). Most of the
tests in test_repositories.py exercise that path: schema, constraints, FKs, and that queries scope
correctly by argument.

For the tables a real signed-in user also reads directly through supabase-js (user_profiles,
meal_plans, plan_items, ...), that's not the whole picture: it doesn't prove RLS itself rejects
cross-user access if a repository function were ever called with the wrong user id, or reused
from a less-privileged connection. test_rls_enforcement.py exercises those same repository
functions over a connection switched to the `authenticated` role with `request.jwt.claim.sub` set
(mirroring supabase/tests/helpers.mjs's asUser/asAnon), so cross-user denial is asserted at the
RLS layer itself — not just inferred from supabase/tests/rls.test.mjs's client-path coverage or
MP-023's mobile-side cross-user test, which cover the same guarantee from a different angle.

Skips (not fails) when no local Postgres is reachable — set POSTGRES_TEST_HOST/PORT/USER/PASSWORD
to point at one; defaults match the CI service container and a `service postgresql start` local
dev setup.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.rows import DictRow, dict_row

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"

_AUTH_STUB_SQL = """
create schema if not exists auth;
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid()
);
create or replace function auth.uid() returns uuid as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$ language sql stable;
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role;
  end if;
end $$;
grant usage on schema auth to authenticated, anon, service_role;
grant execute on function auth.uid() to authenticated, anon, service_role;
grant select, insert on auth.users to authenticated, service_role;
"""


def _admin_conn_params() -> dict[str, str | int]:
    return {
        "host": os.environ.get("POSTGRES_TEST_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_TEST_PORT", "5432")),
        "user": os.environ.get("POSTGRES_TEST_USER", "postgres"),
        "password": os.environ.get("POSTGRES_TEST_PASSWORD", "postgres"),
        "dbname": "postgres",
    }


def _postgres_available() -> bool:
    try:
        with psycopg.connect(**_admin_conn_params(), connect_timeout=3):
            return True
    except psycopg.OperationalError:
        return False


@pytest.fixture(scope="session")
def pg_dsn() -> Iterator[dict[str, str | int]]:
    if not _postgres_available():
        pytest.skip(
            "No local Postgres reachable for MP-031 integration tests. Set "
            "POSTGRES_TEST_HOST/PORT/USER/PASSWORD to point at one."
        )

    db_name = f"mealmate_test_{uuid.uuid4().hex[:8]}"
    admin_params = _admin_conn_params()
    with psycopg.connect(**admin_params, autocommit=True) as admin_conn:
        admin_conn.execute(f'create database "{db_name}"')

    db_params = {**admin_params, "dbname": db_name}
    with psycopg.connect(**db_params, autocommit=True) as conn:
        conn.execute(_AUTH_STUB_SQL)
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.execute(sql_file.read_text(encoding="utf-8"))

    yield db_params

    with psycopg.connect(**admin_params, autocommit=True) as admin_conn:
        admin_conn.execute(f'drop database if exists "{db_name}" with (force)')


@pytest.fixture
def conn(pg_dsn: dict[str, str | int]) -> Iterator[psycopg.Connection[DictRow]]:
    """One connection per test, rolled back at teardown for isolation between tests without
    rebuilding the database each time.
    """
    with psycopg.connect(**pg_dsn, row_factory=dict_row) as connection:
        yield connection
        connection.rollback()


@pytest.fixture
def make_user(conn: psycopg.Connection[DictRow]):
    """Inserts an auth.users row plus a minimal user_profiles row and returns the id — every
    user-owned table (favorites, plans, jobs, notifications, availability) FKs to user_profiles,
    not directly to auth.users, so both are needed for those repository tests to have a valid
    owner to attach rows to.
    """

    def _make_user(user_id: uuid.UUID | None = None, *, grocery_day: str = "monday") -> uuid.UUID:
        user_id = user_id or uuid.uuid4()
        conn.execute("insert into auth.users (id) values (%s)", (user_id,))
        conn.execute(
            "insert into user_profiles (id, dietary_restrictions, grocery_day) "
            "values (%s, %s, %s)",
            (user_id, [], grocery_day),
        )
        return user_id

    return _make_user


@pytest.fixture
def as_authenticated_user(conn: psycopg.Connection[DictRow]):
    """Switches `conn` to the `authenticated` Postgres role with `request.jwt.claim.sub` set to
    the given user id — the same session-level mechanism supabase/tests/helpers.mjs's asUser()
    uses, and what auth.uid() (0006's RLS policies) actually reads. `SET` (not `SET LOCAL`) is
    transactional in Postgres, so this reverts automatically with the `conn` fixture's teardown
    rollback — no explicit reset needed between tests.
    """

    def _as(user_id: uuid.UUID) -> None:
        conn.execute("set role authenticated")
        # set_config (not a literal `SET ... = %s`, which Postgres doesn't accept a bind
        # parameter for) is the parameterized way to set a custom GUC.
        conn.execute("select set_config('request.jwt.claim.sub', %s, false)", (str(user_id),))

    return _as
