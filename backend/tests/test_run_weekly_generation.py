from __future__ import annotations

import datetime
import uuid

import pytest

from app.models import UserProfile
from scripts import run_weekly_generation


class _Connection:
    def __init__(self) -> None:
        self.rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1


def _profile(*, planning_mode: str = "reserves", grocery_day: str = "monday") -> UserProfile:
    return UserProfile(
        id=uuid.uuid4(),
        nonveg_days_per_week=1,
        nonveg_day_pattern=["wed"],
        dietary_restrictions=[],
        dinner_style="rice",
        planning_mode=planning_mode,
        grocery_day=grocery_day,
        timezone="Asia/Kolkata",
    )


def test_week_start_uses_the_triggering_grocery_day_occurrence() -> None:
    grocery_monday = datetime.date(2026, 8, 24)

    assert run_weekly_generation._week_start_for_grocery_day(grocery_monday) == datetime.date(
        2026, 8, 24
    )


def test_sweep_reuses_catalog_and_recovers_connection_after_one_profile_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _profile(planning_mode="reserves", grocery_day="monday")
    second = _profile(planning_mode="suggestion", grocery_day="wednesday")
    monkeypatch.setattr(
        run_weekly_generation.profiles_repo,
        "list_profiles",
        lambda conn: [first, second],
    )
    shared_catalog = (object(),)
    catalog_loads = 0

    def build_catalog(conn):
        nonlocal catalog_loads
        catalog_loads += 1
        return shared_catalog

    monkeypatch.setattr(run_weekly_generation, "build_generation_catalog", build_catalog)
    calls = []

    def generate(conn, user_id, week_start, generator, *, catalog):
        calls.append((user_id, week_start, catalog))
        if user_id == first.id:
            raise RuntimeError("transient claim failure")
        return None

    monkeypatch.setattr(run_weekly_generation, "run_generation_engine", generate)
    conn = _Connection()

    result = run_weekly_generation.run_sweep(  # type: ignore[arg-type]
        conn,
        datetime.date(2026, 8, 25),
        object(),
        None,
    )

    assert catalog_loads == 1
    assert [week_start for _, week_start, _ in calls] == [
        datetime.date(2026, 8, 24),
        datetime.date(2026, 8, 24),
    ]
    assert all(catalog is shared_catalog for _, _, catalog in calls)
    assert conn.rollbacks == 1
    assert result == run_weekly_generation.SweepResult(
        generated=0,
        skipped=1,
        failed=1,
        notified=0,
    )
