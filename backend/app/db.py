"""MP-029: Postgres connection built from typed config (MP-014).

The single place app/repositories/ functions get a connection from, so there's one DB-access
path (reusing app/config.py) rather than each repository opening its own connection differently.
Connects with the same host/port/user/password shape supabase/apply_migrations.py already uses,
now typed on SupabaseConfig instead of read ad hoc from os.environ.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import DictRow, dict_row

from app.config import AppConfig


@contextmanager
def connect(config: AppConfig) -> Iterator[psycopg.Connection[DictRow]]:
    """Yields a connection whose rows come back as dicts (column name -> value), matching what
    app.models.*.model_validate() expects. Commits on clean exit, rolls back on exception —
    callers own transaction boundaries; repository functions never commit internally.
    """
    with psycopg.connect(
        host=config.supabase.db_host,
        port=config.supabase.db_port,
        dbname="postgres",
        user=config.supabase.db_user,
        password=config.supabase.db_password,
        sslmode="require",
        connect_timeout=15,
        row_factory=dict_row,
    ) as conn:
        yield conn
