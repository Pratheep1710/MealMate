"""MP-020: catalog coverage validation — the hard gate before MP-034/MP-038 (generation engine)
can safely start.

Checks, against the live `dishes` table, that every (item_type, veg_or_nonveg) combination the
schema itself defines has a non-zero candidate count, unfiltered and under every combination of
simultaneous dietary_flags hard exclusions a user could plausibly select (mirroring
backend/app/repositories/catalog.py's get_candidates array-overlap exclusion, which takes a whole
list of flags at once — a real user with two allergies excludes on both simultaneously, not one at
a time). PR #12 review finding: an earlier version only checked one flag excluded at a time, which
can pass every single-flag check while still having zero candidates for someone excluding, say,
both Gluten and Nuts together.

MP-034's actual combo templates (which slots need which item_types together) don't exist yet — this
validates at the level MP-003's coverage gate itself describes ("every (slot, item_type)
combination... for both veg and non-veg... under at least the common dietary_flags exclusions"),
which is everything checkable before that later dependency lands. Re-run this once MP-034's
templates exist to validate the actual per-slot combinations, not just the per-item_type/diet cross
product this covers now.

Usage:
  python supabase/seed/validate_coverage.py
Reads connection details from the same SUPABASE_DB_* env vars as apply_migrations.py. Exits 1 if
any zero-candidate combination is found (a real gap to report back, not round away — Phase 5 brief
§2 MP-020).
"""

from __future__ import annotations

import itertools
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


def _minimal_failing_flag_sets(
    flag_sets: list[frozenset[str]], all_flags: tuple[str, ...] = DIETARY_FLAGS
) -> list[frozenset[str]]:
    """Every dish in a group carries some set of dietary_flags (possibly empty). A candidate
    exclusion-set S "fails" (zero candidates survive) when every dish has at least one flag in S —
    i.e. no dish's flags are disjoint from S. Returns the *minimal* failing sets only: if
    excluding just {Gluten} already fails, {Gluten, Nuts} is a trivial consequence (adding more
    exclusions can only remove more candidates, never add them back) and isn't reported
    separately — reporting every superset of an already-failing set would bury the one fact that
    actually matters (which single flag or minimal combination is the real blocker) under
    combinatorial noise. In-memory over a fetched flag list, not one query per subset — cheap even
    at the full 2^6 - 1 = 63 non-empty subsets of the 6-flag vocabulary.
    """
    if not flag_sets:
        return []  # the caller handles a fully-empty group as its own "0 candidates" gap

    def fails(subset: frozenset[str]) -> bool:
        return all(fs & subset for fs in flag_sets)

    minimal: list[frozenset[str]] = []
    for size in range(1, len(all_flags) + 1):
        for combo in itertools.combinations(all_flags, size):
            subset = frozenset(combo)
            if any(subset >= m for m in minimal):
                continue  # already implied by a smaller minimal failing set
            if fails(subset):
                minimal.append(subset)
    return minimal


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
                cur.execute(
                    "select dietary_flags from dishes where item_type = %s and veg_or_nonveg = %s",
                    (item_type, diet),
                )
                flag_sets = [frozenset(row[0]) for row in cur.fetchall()]

                if not flag_sets:
                    gaps.append(f"{item_type} / {diet}: 0 candidates unfiltered")
                    continue  # no point checking exclusions on an already-empty group
                if len(flag_sets) < 3:
                    warnings.append(f"{item_type} / {diet}: only {len(flag_sets)} candidate(s) unfiltered")

                for subset in _minimal_failing_flag_sets(flag_sets):
                    label = " + ".join(sorted(subset))
                    gaps.append(f"{item_type} / {diet}, excluding [{label}]: 0 candidates")
    return gaps, warnings


def main() -> int:
    conn = _connect()
    try:
        gaps, warnings = validate(conn)
    finally:
        conn.close()

    print(
        f"Checked {len(ITEM_TYPES) * len(VEG_OR_NONVEG)} (item_type, veg_or_nonveg) groups against "
        f"every combination of the {len(DIETARY_FLAGS)}-flag vocabulary a user could exclude "
        "simultaneously."
    )

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

    print("\nNo zero-candidate gaps, single flag or in combination. MP-020 gate PASSES.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
