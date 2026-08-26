"""Bulk-loads dishes from the real Tamil Nadu dish workbook (docs/MP-015-catalog-blocked.md's
"dish workbook" / docs/MP-003-catalog-target-decision.md's `Tamil_Nadu_Dishes_Master_Catalogue`,
"Master Dishes" sheet) into the `dishes` table.

DEV-ONLY scaffolding, same as dev_placeholder_dishes.sql — this is a pragmatic bulk import of
`dishes.name`/`item_type`/`veg_or_nonveg`/`region_style` only. It is explicitly NOT MP-015's
taxonomy mapping, MP-016's canonical ingredients, MP-017's dietary-flag tagging, or MP-018's
formal ingestion pipeline (all of that stays blocked pending those decisions — `dietary_flags` is
left at the schema default `{}` and no `ingredients`/`dish_ingredients` rows are written here).
Running this does not clear MP-020's coverage gate.

`Dish Family` values that are condiments/accompaniments rather than standalone meal-slot dishes
(Chutney, Accompaniment, Thuvaiyal, Pachadi, Masiyal/Gothsu) are skipped — they don't map cleanly
to any of the schema's item_type values and aren't something a slot would be filled with on their
own. Every remaining row's name is checked case-insensitively against dishes already in the
database (including the ~20 from dev_placeholder_dishes.sql) and skipped if already present, so
this can be re-run against an updated workbook without creating duplicates.

Usage:
  python supabase/seed/load_master_catalogue.py path/to/Tamil_Nadu_Dishes_Master_Catalogue.xlsx
Reads connection details from the same SUPABASE_DB_* env vars as apply_migrations.py/run_seed.py.
"""

from __future__ import annotations

import os
import sys

import openpyxl
import psycopg

_FAMILY_TO_ITEM_TYPE = {
    "Snack": "snack",
    "Kuzhambu": "gravy",
    "Tiffin": "tiffin",
    "Varuval/Roast": "poriyal",
    "Kootu": "kootu",
    "Sweet": "sweet",
    "Poriyal": "poriyal",
    "Sambar": "gravy",
    "Rice dish": "rice",
    "Rasam": "gravy",
    "Traditional drink/porridge": "snack",
}

_DIET_TO_VEG_OR_NONVEG = {
    "Vegetarian": "veg",
    "Non-Vegetarian": "nonveg",
    "Egg": "nonveg",  # no separate "eggetarian" category in this schema's binary field
}


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


def _load_candidates(xlsx_path: str) -> list[tuple[str, str, str, str | None]]:
    """Returns (name, item_type, veg_or_nonveg, region_style) tuples for every mappable row."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb["Master Dishes"]
    candidates = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        family = row[3]
        item_type = _FAMILY_TO_ITEM_TYPE.get(family)
        if item_type is None:
            continue
        name = (row[5] or "").strip()
        diet = row[2]
        veg_or_nonveg = _DIET_TO_VEG_OR_NONVEG.get(diet)
        if not name or veg_or_nonveg is None:
            continue
        region_style = row[9] or None
        candidates.append((name, item_type, veg_or_nonveg, region_style))
    return candidates


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python load_master_catalogue.py path/to/workbook.xlsx", file=sys.stderr)
        return 1
    xlsx_path = sys.argv[1]

    candidates = _load_candidates(xlsx_path)
    print(f"{len(candidates)} candidate rows map to a known item_type.")

    conn = _connect()
    try:
        existing = conn.execute("select lower(name) from dishes").fetchall()
        existing_names = {row[0] for row in existing}

        seen_this_batch: set[str] = set()
        to_insert = []
        for name, item_type, veg_or_nonveg, region_style in candidates:
            key = name.lower()
            if key in existing_names or key in seen_this_batch:
                continue
            seen_this_batch.add(key)
            to_insert.append((name, item_type, veg_or_nonveg, region_style))

        print(f"{len(candidates) - len(to_insert)} already present (skipped), {len(to_insert)} new.")

        with conn.cursor() as cur:
            cur.executemany(
                "insert into dishes (name, item_type, veg_or_nonveg, region_style) "
                "values (%s, %s, %s, %s)",
                to_insert,
            )
        conn.commit()
        print(f"Inserted {len(to_insert)} dishes.")
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
