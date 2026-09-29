"""Phase 9 (MP-092/093/094): shared FastAPI dependencies for the live app/main.py routes — one
place they get a validated AppConfig and a request-scoped DB connection from, the FastAPI-request
equivalent of app/db.py already being the one place repository functions get a connection from a
script's single long-lived connection.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

import psycopg
from fastapi import Depends
from psycopg.rows import DictRow

from app.config import AppConfig, load_config
from app.db import connect


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Cached for the life of the process — env vars don't change at runtime. Tests override this
    dependency directly via app.dependency_overrides rather than relying on real env vars, so the
    cache never leaks a stale config between test cases.
    """
    return load_config()


def get_db(config: AppConfig = Depends(get_config)) -> Iterator[psycopg.Connection[DictRow]]:
    with connect(config) as conn:
        yield conn
