"""MP-018: tests for supabase/seed/ingest_catalog.py — the real, re-runnable catalog ingestion
pipeline (not load_master_catalogue.py's one-time bulk load).

`load_candidates` tests mirror test_load_master_catalogue.py's approach (a synthetic workbook,
loaded by file path). The idempotency test is the AC this module exists to satisfy: running the
same input twice must not create duplicate rows or error on the second run — asserted against a
real throwaway Postgres database (conftest.py's `conn`/`pg_dsn` fixtures), migrated with the real
supabase/migrations/*.sql including 0016's unique index this pipeline's upsert relies on.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import openpyxl
import psycopg
import pytest

_SEED_DIR = Path(__file__).resolve().parents[2] / "supabase" / "seed"
if str(_SEED_DIR) not in sys.path:
    sys.path.insert(0, str(_SEED_DIR))

import ingest_catalog  # noqa: E402

_COLUMNS = (
    "Dish ID", "Meal Category", "Diet", "Dish Family", "Subfamily / Parent",
    "Specific Dish Variety", "Tamil Name", "Main Ingredient(s)", "Preparation Style",
    "Region / Style",
)


def _row(
    diet: str = "Vegetarian",
    family: str | None = "Poriyal",
    subfamily: str | None = "Poriyal",
    name: str = "Test Dish",
    main_ingredients: str | None = "Cabbage",
    region: str | None = "Tamil Nadu",
) -> tuple:
    return (None, None, diet, family, subfamily, name, None, main_ingredients, None, region)


def _workbook(rows: list[tuple]) -> str:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Master Dishes"
    ws.append(list(_COLUMNS))
    for row in rows:
        ws.append(row)
    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    wb.save(path)
    return path


class TestLoadCandidates:
    def test_a_known_family_and_diet_maps_fully(self) -> None:
        path = _workbook([_row(family="Kuzhambu", name="Sample Kuzhambu")])

        candidates, report = ingest_catalog.load_candidates(path)

        assert len(candidates) == 1
        c = candidates[0]
        assert (c.name, c.item_type, c.veg_or_nonveg) == ("Sample Kuzhambu", "gravy", "veg")
        assert c.meat_type is None
        assert c.track_variety is True
        assert report.inserted == 0  # load_candidates doesn't write, only ingest() does

    def test_a_condiment_only_family_is_skipped(self) -> None:
        path = _workbook([_row(family="Chutney", name="Coconut Chutney")])

        candidates, report = ingest_catalog.load_candidates(path)

        assert candidates == []
        assert report.skipped_condiment == 1

    def test_an_unrecognized_family_is_reported_not_dropped_silently(self) -> None:
        path = _workbook([_row(family="Not A Real Family", name="Mystery")])

        candidates, report = ingest_catalog.load_candidates(path)

        assert candidates == []
        assert report.skipped_unmapped_family == ["Mystery"]

    def test_an_unrecognized_diet_is_reported(self) -> None:
        path = _workbook([_row(diet="Vegan", name="Vegan Thing")])

        candidates, report = ingest_catalog.load_candidates(path)

        assert candidates == []
        assert report.skipped_unmapped_diet == ["Vegan Thing"]

    def test_rice_and_curd_get_track_variety_false(self) -> None:
        path = _workbook(
            [
                _row(family="Rice dish", name="Lemon Rice"),
                _row(family="Poriyal", name="Curd Rice"),  # item_type resolution is by family only
            ]
        )

        candidates, _ = ingest_catalog.load_candidates(path)

        rice = next(c for c in candidates if c.name == "Lemon Rice")
        assert rice.track_variety is False

    def test_nonveg_dish_gets_meat_type_and_report_stays_clean_when_resolved(self) -> None:
        path = _workbook(
            [_row(diet="Non-Vegetarian", family="Kuzhambu", subfamily="Chicken gravy",
                  name="Chicken Salna", main_ingredients="Chicken")]
        )

        candidates, report = ingest_catalog.load_candidates(path)

        assert candidates[0].meat_type == "chicken"
        assert report.unresolved_meat_type == []

    def test_unresolvable_nonveg_meat_type_is_reported(self) -> None:
        path = _workbook(
            [_row(diet="Non-Vegetarian", family="Snack", subfamily="Non-veg snack",
                  name="Mystery Snack", main_ingredients=None)]
        )

        candidates, report = ingest_catalog.load_candidates(path)

        assert candidates[0].meat_type is None
        assert report.unresolved_meat_type == ["Mystery Snack"]

    def test_duplicate_names_within_the_workbook_are_reported_and_only_the_first_kept(self) -> None:
        path = _workbook(
            [
                _row(name="Repeated Dish", main_ingredients="Cabbage"),
                _row(name="repeated dish", main_ingredients="Carrot"),  # case-insensitive dup
            ]
        )

        candidates, report = ingest_catalog.load_candidates(path)

        assert len(candidates) == 1
        assert report.duplicate_in_batch == ["repeated dish"]

    def test_dietary_flags_are_populated_from_ingredients(self) -> None:
        path = _workbook([_row(name="Milk Sweet", main_ingredients="Milk + sugar")])

        candidates, _ = ingest_catalog.load_candidates(path)

        assert "Milk-Dairy" in candidates[0].dietary_flags


class TestIngestIdempotency:
    @pytest.fixture
    def clean_dishes(self, conn: psycopg.Connection):
        # ingest() commits for real (dry_run=False mirrors production) — pg_dsn is a session-scoped
        # database shared with every other test file, so unlike the rest of this suite (which
        # relies on the `conn` fixture's teardown rollback for isolation), these tests must commit
        # their own cleanup on both sides of the test rather than leaving debris for whatever runs
        # next in the shared database.
        conn.execute("delete from dishes")
        conn.commit()
        yield
        conn.execute("delete from dishes")
        conn.commit()

    def test_running_the_same_workbook_twice_creates_no_duplicates(
        self, conn, clean_dishes
    ) -> None:
        path = _workbook(
            [
                _row(name="Idempotency Test Dish One", main_ingredients="Cabbage"),
                _row(name="Idempotency Test Dish Two", diet="Non-Vegetarian", family="Kuzhambu",
                     subfamily="Chicken gravy", main_ingredients="Chicken"),
            ]
        )
        candidates, report = ingest_catalog.load_candidates(path)

        ingest_catalog.ingest(conn, candidates, report, dry_run=False)
        assert (report.inserted, report.updated) == (2, 0)

        row_count_after_first = conn.execute("select count(*) as n from dishes").fetchone()["n"]
        assert row_count_after_first == 2

        # Re-run: fresh report, same candidates, same connection — must update, not duplicate/error.
        candidates_again, report_again = ingest_catalog.load_candidates(path)
        ingest_catalog.ingest(conn, candidates_again, report_again, dry_run=False)

        assert (report_again.inserted, report_again.updated) == (0, 2)
        row_count_after_second = conn.execute("select count(*) as n from dishes").fetchone()["n"]
        assert row_count_after_second == 2

    def test_a_re_run_refreshes_taxonomy_but_leaves_track_variety_alone(
        self, conn, clean_dishes
    ) -> None:
        conn.execute(
            "insert into dishes (name, item_type, veg_or_nonveg, track_variety) "
            "values ('Existing Rice Dish', 'rice', 'veg', true)"
        )
        # Hand-curated override: this dish was manually marked track_variety=true even though the
        # systematic rule for item_type='rice' is false — the pipeline must not overwrite it.
        path = _workbook(
            [_row(family="Rice dish", name="Existing Rice Dish", main_ingredients="Milk")]
        )
        candidates, report = ingest_catalog.load_candidates(path)

        ingest_catalog.ingest(conn, candidates, report, dry_run=False)

        row = conn.execute(
            "select track_variety, dietary_flags from dishes where name = 'Existing Rice Dish'"
        ).fetchone()
        assert row["track_variety"] is True  # untouched
        assert "Milk-Dairy" in row["dietary_flags"]  # taxonomy still refreshed from the workbook

    def test_dry_run_does_not_commit(self, conn, clean_dishes) -> None:
        path = _workbook([_row(name="Dry Run Dish")])
        candidates, report = ingest_catalog.load_candidates(path)

        ingest_catalog.ingest(conn, candidates, report, dry_run=True)

        # dry_run rolls back inside ingest() itself, on the same connection/transaction — nothing
        # to commit from the test side; a fresh statement on the same conn sees the rollback.
        count = conn.execute(
            "select count(*) as n from dishes where name = 'Dry Run Dish'"
        ).fetchone()["n"]
        assert count == 0
