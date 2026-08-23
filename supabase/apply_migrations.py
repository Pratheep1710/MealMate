"""One-time schema apply against a live Supabase project (MP-006/007-011/013).

Not a migration framework — this repo doesn't track applied-migration state anywhere (no
supabase_migrations table), because it's meant to run once against a fresh project. Re-running it
against a project that already has these tables will fail loudly on the first `create table` — that
failure is the correct signal, not a bug to work around.

Reads connection details from env vars, never from argv or a hardcoded value in this file:
  SUPABASE_DB_HOST      e.g. db.<project-ref>.supabase.co, or a pooler host
  SUPABASE_DB_PORT      defaults to 5432
  SUPABASE_DB_USER      defaults to "postgres"; pooler hosts need "postgres.<project-ref>"
  SUPABASE_DB_PASSWORD  the Postgres password for that role

Direct connection hosts (db.<project-ref>.supabase.co) are often IPv6-only. If that times out from
an IPv4-only network, use the Session Pooler host from the dashboard's Connect panel instead (it's
IPv4-compatible) along with the "postgres.<project-ref>" username it requires.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def main() -> int:
    host = os.environ.get("SUPABASE_DB_HOST")
    password = os.environ.get("SUPABASE_DB_PASSWORD")
    port = int(os.environ.get("SUPABASE_DB_PORT", "5432"))
    user = os.environ.get("SUPABASE_DB_USER", "postgres")
    if not host or not password:
        print("SUPABASE_DB_HOST and SUPABASE_DB_PASSWORD must be set in the environment.", file=sys.stderr)
        return 1

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print(f"No .sql files found in {MIGRATIONS_DIR}", file=sys.stderr)
        return 1

    print(f"Connecting to {host} ...")
    with psycopg.connect(
        host=host,
        port=port,
        dbname="postgres",
        user=user,
        password=password,
        sslmode="require",
        connect_timeout=15,
    ) as conn:
        print("Connected.")
        for file in files:
            sql = file.read_text(encoding="utf-8")
            print(f"Applying {file.name} ...", end=" ")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                conn.commit()
                print("OK")
            except Exception as exc:
                conn.rollback()
                print("FAILED")
                print(f"  {type(exc).__name__}: {exc}", file=sys.stderr)
                return 1

        print("\nVerifying tables ...")
        with conn.cursor() as cur:
            cur.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'public'
                order by table_name
                """
            )
            tables = [row[0] for row in cur.fetchall()]
            for t in tables:
                print(f"  - {t}")

            cur.execute(
                """
                select tablename, count(*) as policy_count
                from pg_policies
                where schemaname = 'public'
                group by tablename
                order by tablename
                """
            )
            print("\nRLS policies per table:")
            for row in cur.fetchall():
                print(f"  - {row[0]}: {row[1]} polic{'y' if row[1] == 1 else 'ies'}")

    print("\nAll migrations applied successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
