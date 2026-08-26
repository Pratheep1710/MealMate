"""MP-020: catalog coverage validation — the hard gate before MP-034/MP-038 (generation engine)
can safely start.

Checks, against the live `dishes` table, that every (item_type, veg_or_nonveg) combination the
schema itself defines has a non-zero candidate count, both unfiltered and under each single
dietary_flags hard exclusion individually (mirroring backend/app/repositories/catalog.py's
get_candidates array-overlap exclusion). MP-034's actual combo templates (which slots need which
item_types together) don't exist yet — this validates at the level MP-003's coverage gate itself
describes ("every (slot, item_type) combination... for both veg and non-veg... under at least the
common dietary_flags exclusions"), which is everything checkable before that later dependency
lands. Re-run this once MP-034's templates exist to validate the actual per-slot combinations, not
just the per-item_type/diet/flag cross product this covers now.

Usage:
  python supabase/seed/validate_coverage.py
Reads connection details from the same SUPABASE_DB_* env vars as apply_migrations.py. Exits 1 if
any zero-candidate combination is found (a real gap to report back, not round away — Phase 5 brief
§2 MP-020).
"""

from __future__ import annotations

import os
import sys

import psycopg

ITEM_TYPES = ("tiffin", "rice", "gravy", "poriyal", "kootu", "curd", "snack", "sweet")
VEG_OR_NONVEG = ("veg", "nonveg")
DIETARY_FLAGS = ("Nuts", "Milk-Dairy", "Gluten", "Egg", "Seafood", "Sesame")


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


def _count(cur: psycopg.Cursor, *, item_type: str, veg_or_nonveg: str, exclude_flag: str | None) -> int:
    conditions = ["item_type = %s", "veg_or_nonveg = %s"]
    params: list[object] = [item_type, veg_or_nonveg]
    if exclude_flag is not None:
        conditions.append("not (dietary_flags && %s)")
        params.append([exclude_flag])
    sql = "select count(*) from dishes where " + " and ".join(conditions)
    cur.execute(sql, params)
    (count,) = cur.fetchone()
    return count


def validate(conn: psycopg.Connection) -> tuple[list[str], list[str]]:
    """Returns (zero_candidate_gaps, low_margin_warnings) — gaps are the hard-fail list; warnings
    (candidate count > 0 but small, e.g. < 3) are worth surfacing but don't fail the gate on their
    own, since MP-020's AC is "non-zero", not a minimum margin.
    """
    gaps: list[str] = []
    warnings: list[str] = []
    with conn.cursor(row_factory=psycopg.rows.tuple_row) as cur:
        for item_type in ITEM_TYPES:
            for diet in VEG_OR_NONVEG:
                base_count = _count(cur, item_type=item_type, veg_or_nonveg=diet, exclude_flag=None)
                if base_count == 0:
                    gaps.append(f"{item_type} / {diet}: 0 candidates unfiltered")
                    continue  # no point checking flag exclusions on an already-empty base
                if base_count < 3:
                    warnings.append(f"{item_type} / {diet}: only {base_count} candidate(s) unfiltered")

                for flag in DIETARY_FLAGS:
                    excluded_count = _count(cur, item_type=item_type, veg_or_nonveg=diet, exclude_flag=flag)
                    if excluded_count == 0:
                        gaps.append(f"{item_type} / {diet}, excluding '{flag}': 0 candidates")
    return gaps, warnings


def main() -> int:
    conn = _connect()
    try:
        gaps, warnings = validate(conn)
    finally:
        conn.close()

    total_combos = len(ITEM_TYPES) * len(VEG_OR_NONVEG) * (1 + len(DIETARY_FLAGS))
    print(f"Checked {total_combos} (item_type, veg_or_nonveg, dietary_flag exclusion) combinations.")

    if warnings:
        print(f"\n{len(warnings)} low-margin warning(s) (non-zero but thin — not a gate failure):")
        for w in warnings:
            print(f"  - {w}")

    if gaps:
        print(f"\n{len(gaps)} ZERO-CANDIDATE GAP(S) — MP-020 gate FAILS:")
        for g in gaps:
            print(f"  - {g}")
        print(
            "\nEach of these needs a decision: source more dishes from the master catalogue's "
            "remaining rows (MP-003's fallback), relax which combination is required, or accept "
            "the gap for now — not something this script should silently work around."
        )
        return 1

    print("\nNo zero-candidate gaps. MP-020 gate PASSES.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
