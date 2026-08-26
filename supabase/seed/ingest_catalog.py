"""MP-018: real, re-runnable catalog ingestion pipeline for the master dish workbook.

Not `load_master_catalogue.py` retrofitted — that script was a one-time bulk import with no
idempotency or conflict handling (see its own docstring). This one:
  - upserts by name (case-insensitive) using the unique index from
    0016_dishes_meat_type_and_taxonomy_constraints.sql, so running it twice on the same input
    updates in place rather than erroring or duplicating;
  - maps the full MP-015 taxonomy (item_type, veg_or_nonveg, region_style, meat_type,
    dietary_flags, track_variety for new rows) via catalog_taxonomy.py, not just item_type;
  - reports every unmapped/rejected/low-confidence row instead of silently dropping or defaulting
    it (MP-015's AC).

On conflict (an existing row with the same lower(name)): item_type, veg_or_nonveg, region_style,
meat_type, and dietary_flags are refreshed from the workbook every run, since the workbook is this
data's source of truth. prep_minutes is never touched on conflict — the workbook has no
prep_minutes column at all (a confirmed gap, not an oversight) — and is only ever set on first
insert. track_variety is corrected one-directionally on conflict: an existing `true` is overwritten
if the systematic rule computes `false` for that item_type (fixing rows that were only ever left at
the schema default, never actually decided), but an existing `false` is always left alone (the
schema default is `true`, so a `false` can only exist because something deliberately set it —
e.g. dev_placeholder_dishes.sql's non-rice/curd staple exceptions — and this systematic pass
shouldn't clobber that judgment). See `ingest()`'s own SQL comment for the exact CASE logic.

Usage:
  python supabase/seed/ingest_catalog.py path/to/Tamil_Nadu_Dishes_Master_Catalogue_Claude.xlsx [--dry-run]
Reads connection details from the same SUPABASE_DB_* env vars as apply_migrations.py.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import openpyxl
import psycopg

from catalog_taxonomy import (
    CONDIMENT_ONLY_FAMILIES,
    DIET_TO_VEG_OR_NONVEG,
    FAMILY_TO_ITEM_TYPE,
    NO_VARIETY_ITEM_TYPES,
    infer_dietary_flags,
    infer_meat_type,
)


@dataclass
class Candidate:
    name: str
    item_type: str
    veg_or_nonveg: str
    region_style: str | None
    meat_type: str | None
    dietary_flags: list[str]
    track_variety: bool


@dataclass
class Report:
    total_rows: int = 0
    skipped_condiment: int = 0
    skipped_unmapped_family: list[str] = field(default_factory=list)
    skipped_unmapped_diet: list[str] = field(default_factory=list)
    skipped_no_name: int = 0
    duplicate_in_batch: list[str] = field(default_factory=list)
    low_confidence_meat_type: list[str] = field(default_factory=list)
    unresolved_meat_type: list[str] = field(default_factory=list)
    inserted: int = 0
    updated: int = 0
    committed_through: int = 0  # rows count as of the last successful conn.commit() in ingest()

    def print_summary(self) -> None:
        print(f"\n{self.total_rows} rows read from the workbook.")
        print(f"  {self.skipped_condiment} skipped (condiment-only family, not a standalone dish).")
        if self.skipped_unmapped_family:
            print(f"  {len(self.skipped_unmapped_family)} skipped — unrecognized Dish Family:")
            for name in self.skipped_unmapped_family[:20]:
                print(f"    - {name}")
        if self.skipped_unmapped_diet:
            print(f"  {len(self.skipped_unmapped_diet)} skipped — unrecognized Diet:")
            for name in self.skipped_unmapped_diet[:20]:
                print(f"    - {name}")
        if self.skipped_no_name:
            print(f"  {self.skipped_no_name} skipped — no name.")
        if self.duplicate_in_batch:
            print(f"  {len(self.duplicate_in_batch)} duplicate names within this workbook (first kept):")
            for name in self.duplicate_in_batch[:20]:
                print(f"    - {name}")
        if self.unresolved_meat_type:
            print(
                f"  {len(self.unresolved_meat_type)} non-veg rows with NO identifiable protein "
                "(meat_type left null, needs review):"
            )
            for name in self.unresolved_meat_type[:20]:
                print(f"    - {name}")
        if self.low_confidence_meat_type:
            print(
                f"  {len(self.low_confidence_meat_type)} rows tagged meat_type='other' from a "
                "generic/ambiguous keyword only — worth a human's second look:"
            )
            for name in self.low_confidence_meat_type[:20]:
                print(f"    - {name}")
        print(f"\n  {self.inserted} inserted, {self.updated} updated.")


def _connect() -> psycopg.Connection:
    host = os.environ.get("SUPABASE_DB_HOST")
    password = os.environ.get("SUPABASE_DB_PASSWORD")
    port = int(os.environ.get("SUPABASE_DB_PORT", "5432"))
    user = os.environ.get("SUPABASE_DB_USER", "postgres")
    if not host or not password:
        print("SUPABASE_DB_HOST and SUPABASE_DB_PASSWORD must be set in the environment.", file=sys.stderr)
        raise SystemExit(1)
    return psycopg.connect(
        host=host, port=port, dbname="postgres", user=user, password=password,
        sslmode="require", connect_timeout=15,
    )


def load_candidates(xlsx_path: str) -> tuple[list[Candidate], Report]:
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Master Dishes"]
    report = Report()
    candidates: list[Candidate] = []
    seen: dict[str, str] = {}  # lower(name) -> original name, for within-batch dedup reporting

    for row in ws.iter_rows(min_row=2, values_only=True):
        if row is None or not any(row):
            continue
        report.total_rows += 1

        diet = row[2]
        family = row[3]
        subfamily = row[4]
        name = (row[5] or "").strip()
        main_ingredients = row[7]
        region_style = row[9] or None

        if family in CONDIMENT_ONLY_FAMILIES:
            report.skipped_condiment += 1
            continue

        item_type = FAMILY_TO_ITEM_TYPE.get(family)
        if item_type is None:
            report.skipped_unmapped_family.append(name or f"<unnamed, family={family!r}>")
            continue

        veg_or_nonveg = DIET_TO_VEG_OR_NONVEG.get(diet)
        if veg_or_nonveg is None:
            report.skipped_unmapped_diet.append(name or f"<unnamed, diet={diet!r}>")
            continue

        if not name:
            report.skipped_no_name += 1
            continue

        key = name.lower()
        if key in seen:
            report.duplicate_in_batch.append(name)
            continue
        seen[key] = name

        meat_type, low_confidence = infer_meat_type(
            diet=diet, subfamily=subfamily, name=name, main_ingredients=main_ingredients
        )
        if veg_or_nonveg == "nonveg" and diet == "Non-Vegetarian" and meat_type is None:
            report.unresolved_meat_type.append(name)
        elif low_confidence:
            report.low_confidence_meat_type.append(name)

        dietary_flags = infer_dietary_flags(
            diet=diet, family=family, subfamily=subfamily, name=name, main_ingredients=main_ingredients
        )

        candidates.append(
            Candidate(
                name=name,
                item_type=item_type,
                veg_or_nonveg=veg_or_nonveg,
                region_style=region_style,
                meat_type=meat_type,
                dietary_flags=dietary_flags,
                track_variety=item_type not in NO_VARIETY_ITEM_TYPES,
            )
        )

    return candidates, report


_COMMIT_BATCH_SIZE = 50


def ingest(conn: psycopg.Connection, candidates: list[Candidate], report: Report, *, dry_run: bool) -> None:
    """Commits every `_COMMIT_BATCH_SIZE` rows (real runs only) rather than holding one ~700-row
    transaction open for the whole run — a real run against the workbook's ~690 rows over
    Supabase's pooled connection dropped mid-transaction once with a plain single-commit version
    (`server closed the connection unexpectedly`). Safe to batch precisely because the upsert is
    idempotent: a run that dies partway through just needs a re-run, which will update the
    already-committed rows in place (no-ops) and continue past the ones the drop hadn't reached
    yet — no partial-batch cleanup logic needed.
    """
    # Explicit tuple_row regardless of the connection's own row_factory (test fixtures in this repo
    # default connections to dict_row) — `(was_insert,) = cur.fetchone()` below needs a real tuple,
    # not a dict, whose iteration order isn't the same thing as positional unpacking.
    with conn.cursor(row_factory=psycopg.rows.tuple_row) as cur:
        for i, c in enumerate(candidates):
            cur.execute(
                """
                insert into dishes
                    (name, item_type, veg_or_nonveg, region_style, meat_type, dietary_flags, track_variety)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (lower(name)) do update set
                    item_type = excluded.item_type,
                    veg_or_nonveg = excluded.veg_or_nonveg,
                    region_style = excluded.region_style,
                    meat_type = excluded.meat_type,
                    dietary_flags = excluded.dietary_flags,
                    -- PR #12 review finding: the original version never touched track_variety on
                    -- conflict at all, so the 553 workbook-only rows kept the schema default
                    -- (true) forever, including rice/curd dishes the systematic rule computes as
                    -- false. Fixed one-directionally: only ever correct true -> false (an
                    -- unset-default value drifting to what the systematic rule says it should be),
                    -- never false -> true. A `false` can only exist here because something
                    -- deliberately set it — the schema default is `true` — so it's safe to treat
                    -- any existing `false` as a real hand-curated override (e.g.
                    -- dev_placeholder_dishes.sql's murukku/payasam exceptions) and leave it alone,
                    -- while still fixing every dish that was silently left at the wrong default.
                    track_variety = case
                        when dishes.track_variety = true and excluded.track_variety = false
                            then excluded.track_variety
                        else dishes.track_variety
                    end
                returning (xmax = 0) as inserted
                """,
                (
                    c.name, c.item_type, c.veg_or_nonveg, c.region_style,
                    c.meat_type, c.dietary_flags, c.track_variety,
                ),
            )
            (was_insert,) = cur.fetchone()
            if was_insert:
                report.inserted += 1
            else:
                report.updated += 1

            if not dry_run and (i + 1) % _COMMIT_BATCH_SIZE == 0:
                conn.commit()
                report.committed_through = i + 1

    if dry_run:
        conn.rollback()
    else:
        conn.commit()  # flushes the final partial batch
        report.committed_through = len(candidates)


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv[1:]
    if len(args) != 1:
        print("Usage: python ingest_catalog.py path/to/workbook.xlsx [--dry-run]", file=sys.stderr)
        return 1

    candidates, report = load_candidates(args[0])
    conn = _connect()
    try:
        ingest(conn, candidates, report, dry_run=dry_run)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass  # connection may already be dead (e.g. the drop that caused this failure)
        # ingest() commits in batches of _COMMIT_BATCH_SIZE, so a mid-run failure can leave earlier
        # batches already committed — only the batch in flight when this failed is rolled back.
        # Safe to just re-run: the upsert is idempotent, so already-committed rows are no-ops.
        print(
            f"FAILED — {report.committed_through} of {len(candidates)} rows were committed in "
            "earlier batches before this happened; the in-flight batch was rolled back. Re-run "
            "the same command — the upsert is idempotent, so already-committed rows are updated "
            "in place as no-ops and the run picks up from where it stopped.",
            file=sys.stderr,
        )
        print(f"  {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    report.print_summary()
    if dry_run:
        print("\n--dry-run: rolled back, no changes were actually committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
