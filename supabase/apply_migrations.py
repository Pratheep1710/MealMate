"""Schema migration runner for the live Supabase project (MP-006/007-011/013).

Review fix (PR #1): the original version committed each file separately with no history
tracking, so a mid-batch failure (e.g. file 4 of 6) left files 1-3 permanently applied with no
record of what ran, and a rerun failed immediately re-trying file 1. This version fixes both
problems:
  - Idempotent/resumable: applied migrations are recorded in `_migrations.history` (filename +
    sha256 checksum + timestamp), so a rerun skips anything already applied and only executes
    what's new. A file whose content changed after being recorded is treated as drift and blocks
    the run rather than silently re-applying a rewritten migration.
  - Atomic: every *pending* migration in a run applies inside a single transaction. If any one of
    them fails, the whole batch rolls back — no partial state, no follow-up file failing against
    a database that's already half-migrated.

Reads connection details from env vars, never from argv or a hardcoded value in this file:
  SUPABASE_DB_HOST      e.g. db.<project-ref>.supabase.co, or a pooler host
  SUPABASE_DB_PORT      defaults to 5432
  SUPABASE_DB_USER      defaults to "postgres"; pooler hosts need "postgres.<project-ref>"
  SUPABASE_DB_PASSWORD  the Postgres password for that role

Direct connection hosts (db.<project-ref>.supabase.co) are often IPv6-only. If that times out from
an IPv4-only network, use the Session Pooler host from the dashboard's Connect panel instead (it's
IPv4-compatible) along with the "postgres.<project-ref>" username it requires.

Usage:
  python apply_migrations.py                     Apply every pending migration (one transaction).
  python apply_migrations.py --mark-applied FILE...
                                                   Record FILE(s) as applied WITHOUT running their
                                                   SQL. For reconciling migrations that were already
                                                   applied by hand before this tracking table
                                                   existed — never for skipping a real apply.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

HISTORY_DDL = """
create schema if not exists _migrations;
create table if not exists _migrations.history (
    filename text primary key,
    checksum text not null,
    applied_at timestamptz not null default now()
);
"""


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _connect() -> psycopg.Connection:
    host = os.environ.get("SUPABASE_DB_HOST")
    password = os.environ.get("SUPABASE_DB_PASSWORD")
    port = int(os.environ.get("SUPABASE_DB_PORT", "5432"))
    user = os.environ.get("SUPABASE_DB_USER", "postgres")
    if not host or not password:
        print("SUPABASE_DB_HOST and SUPABASE_DB_PASSWORD must be set in the environment.", file=sys.stderr)
        raise SystemExit(1)

    print(f"Connecting to {host} ...")
    conn = psycopg.connect(
        host=host,
        port=port,
        dbname="postgres",
        user=user,
        password=password,
        sslmode="require",
        connect_timeout=15,
    )
    print("Connected.")
    return conn


def _load_history(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(HISTORY_DDL)
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("select filename, checksum from _migrations.history")
        return dict(cur.fetchall())


def mark_applied(conn: psycopg.Connection, filenames: list[str]) -> int:
    """Record filenames as applied without executing them — for backfilling history against a
    database where they were already applied by hand, never for skipping a real migration."""
    applied = _load_history(conn)
    with conn.cursor() as cur:
        for name in filenames:
            path = MIGRATIONS_DIR / name
            if not path.is_file():
                print(f"No such migration file: {name}", file=sys.stderr)
                return 1
            checksum = _checksum(path.read_text(encoding="utf-8"))
            if name in applied:
                print(f"{name}: already recorded, skipping")
                continue
            cur.execute(
                "insert into _migrations.history (filename, checksum) values (%s, %s)",
                (name, checksum),
            )
            print(f"{name}: recorded as applied (not executed)")
    conn.commit()
    return 0


def apply_pending(conn: psycopg.Connection) -> int:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print(f"No .sql files found in {MIGRATIONS_DIR}", file=sys.stderr)
        return 1

    applied = _load_history(conn)

    pending: list[tuple[Path, str, str]] = []
    for file in files:
        sql = file.read_text(encoding="utf-8")
        checksum = _checksum(sql)
        if file.name in applied:
            if applied[file.name] != checksum:
                print(
                    f"DRIFT: {file.name} is recorded as applied with a different checksum than "
                    "the file on disk now has. Never edit an already-applied migration — add a "
                    "new numbered file instead. Refusing to run until this is resolved.",
                    file=sys.stderr,
                )
                return 1
            print(f"{file.name}: already applied, skipping")
            continue
        pending.append((file, sql, checksum))

    if not pending:
        print("\nNothing to apply — database is already up to date.")
        return 0

    print(f"\nApplying {len(pending)} pending migration(s) in one transaction ...")
    try:
        with conn.cursor() as cur:
            for file, sql, checksum in pending:
                print(f"  {file.name} ...", end=" ")
                cur.execute(sql)
                cur.execute(
                    "insert into _migrations.history (filename, checksum) values (%s, %s)",
                    (file.name, checksum),
                )
                print("OK")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print("FAILED — rolled back the entire batch, database unchanged.", file=sys.stderr)
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
        for row in cur.fetchall():
            print(f"  - {row[0]}")

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

    print("\nAll pending migrations applied successfully.")
    return 0


def main() -> int:
    args = sys.argv[1:]
    conn = _connect()
    try:
        if args and args[0] == "--mark-applied":
            return mark_applied(conn, args[1:])
        return apply_pending(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
