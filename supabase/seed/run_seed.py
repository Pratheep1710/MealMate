"""Runs dev_placeholder_dishes.sql against the live Supabase project.

DEV-ONLY scaffolding — not part of the tracked migration history (supabase/apply_migrations.py),
and never counted toward MP-020's catalog coverage validation. See dev_placeholder_dishes.sql's
header for what this seeds and why.

Reads the same connection env vars as apply_migrations.py:
  SUPABASE_DB_HOST      e.g. db.<project-ref>.supabase.co, or a pooler host
  SUPABASE_DB_PORT      defaults to 5432
  SUPABASE_DB_USER      defaults to "postgres"; pooler hosts need "postgres.<project-ref>"
  SUPABASE_DB_PASSWORD  the Postgres password for that role

Usage:
  python supabase/seed/run_seed.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

SEED_FILE = Path(__file__).parent / "dev_placeholder_dishes.sql"


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


def main() -> int:
    conn = _connect()
    try:
        sql = SEED_FILE.read_text(encoding="utf-8")
        print(f"Running {SEED_FILE.name} ...")
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print("Seed applied.")
        return 0
    except Exception as exc:
        conn.rollback()
        print("FAILED — rolled back, database unchanged.", file=sys.stderr)
        print(f"  {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
