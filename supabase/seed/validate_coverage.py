"""MP-020: catalog coverage validation, including the slot/combo-template dimension.

Checks, against the live `dishes` table, that every (item_type, veg_or_nonveg) combination the
schema itself defines has a non-zero candidate count, unfiltered and under every combination of
simultaneous dietary_flags hard exclusions a user could plausibly select (mirroring
backend/app/repositories/catalog.py's get_candidates array-overlap exclusion, which takes a whole
list of flags at once — a real user with two allergies excludes on both simultaneously, not one at
a time). PR #12 review round 1 finding: an earlier version only checked one flag excluded at a
time, which can pass every single-flag check while still having zero candidates for someone
excluding, say, both Gluten and Nuts together.

**Slot/combo-template severity classification (PR #12 review round 2)** — every gap is now
labeled BLOCKING (a real slot's combo template needs this item_type — see SLOT_ITEM_TYPES below,
sourced directly from version1_mealPlanner_technical.md §5 and
version1_mealPlanner_functionalities.md, supplied by Pratheep for this exact purpose) or
NOT TEMPLATE-REQUIRED (no known slot's template needs this item_type — it only matters for the
edit-time "+ add a missing item_type" flow, functional spec §6, not for MP-034's core weekly
generation). This is a real distinction, not a softened one: the source specs' only worked combo
example (afternoon/lunch) never mentions kootu, curd, or sweet, and neither document assigns them
to any slot anywhere — so a zero-candidate kootu/curd/sweet combination cannot block generation
itself, only a user's optional edit-time substitution into a slot that doesn't ask for it by
default. See SLOT_ITEM_TYPES's own comments for exactly which mappings are verbatim from the specs
vs. reasonably inferred (labeled explicitly either way — nothing here is invented without saying
so). The gate (exit code) now fails only on a BLOCKING gap; NOT TEMPLATE-REQUIRED gaps are still
reported in full, just not gating.

Usage:
  python supabase/seed/validate_coverage.py
Reads connection details from the same SUPABASE_DB_* env vars as apply_migrations.py. Exits 1 if
any BLOCKING zero-candidate combination is found (a real gap to report back, not round away —
Phase 5 brief §2 MP-020).
"""

from __future__ import annotations

import itertools
import os
import sys

import psycopg

ITEM_TYPES = ("tiffin", "rice", "gravy", "poriyal", "kootu", "curd", "snack", "sweet")
VEG_OR_NONVEG = ("veg", "nonveg")
DIETARY_FLAGS = ("Nuts", "Milk-Dairy", "Gluten", "Egg", "Seafood", "Sesame")

# Sourced from the real spec documents (supplied by Pratheep, PR #12 review round 2) — not every
# slot has a fully explicit worked example, so each entry says exactly what's verbatim vs. inferred
# rather than presenting all six with equal confidence.
SLOT_ITEM_TYPES: dict[str, tuple[str, ...]] = {
    # VERBATIM — technical spec §5, the one worked "slot/combo template" example given:
    # "lunch = 1 rice + 1-2 gravy + 1 poriyal". Coverage only checks existence (>=1 candidate),
    # never the 1-2 gravy upper bound — an upper bound can't create a zero-candidate gap.
    "afternoon": ("rice", "gravy", "poriyal"),
    # INFERRED, not a worked example. Functional spec §2 Q4 asks dinner style as "full rice meal,
    # or tiffin-style" (dinner = night) and neither spec ever names a morning-slot alternative to
    # tiffin — by elimination and standard Tamil Nadu breakfast convention, not a literal quote.
    "morning": ("tiffin",),
    # INFERRED, user_profiles.dinner_style-dependent (technical spec §4's own column comment:
    # "'rice' | 'tiffin' — onboarding question"). A user picks one style at onboarding and can't
    # switch later (mode switching isn't supported post-onboarding), but the catalog must support
    # whichever style a real user picks, so both branches are checked as separate labeled cases.
    "night (dinner_style=rice)": ("rice",),
    "night (dinner_style=tiffin)": ("tiffin",),
    # VERBATIM (structurally) — functional spec §1: "6 slots: morning, afternoon, night, + 3
    # snacks". Each snack slot maps to item_type='snack' by the schema's own naming symmetry; no
    # other item_type is ever associated with a snack slot in either spec.
    "snack_1": ("snack",),
    "snack_2": ("snack",),
    "snack_3": ("snack",),
    # kootu, curd, and sweet are deliberately absent here — neither spec assigns any of the three
    # to a slot anywhere, including in the one worked combo example above (which names rice, gravy,
    # and poriyal specifically and nothing else). Treated as edit-time-optional additions
    # (functional spec §6's "+ to add a missing item_type"), not baseline generation requirements.
}

ITEM_TYPE_TO_SLOTS: dict[str, list[str]] = {}
for _slot, _item_types in SLOT_ITEM_TYPES.items():
    for _item_type in _item_types:
        ITEM_TYPE_TO_SLOTS.setdefault(_item_type, []).append(_slot)


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


def _slot_suffix(item_type: str) -> str:
    slots = ITEM_TYPE_TO_SLOTS.get(item_type)
    if slots:
        return f" [BLOCKS: {', '.join(slots)}]"
    return " [not required by any known slot template — edit-time-only impact]"


def validate(conn: psycopg.Connection) -> tuple[list[str], list[str], list[str]]:
    """Returns (blocking_gaps, non_blocking_gaps, low_margin_warnings).

    A gap is BLOCKING when its item_type appears in SLOT_ITEM_TYPES — a real slot's combo template
    needs it, so a zero-candidate result there would break MP-034's core weekly generation for
    that slot. A gap is non-blocking when no known slot template requires that item_type at all
    (kootu, curd, sweet) — it still means a real limitation (the edit-time "+ add a missing
    item_type" flow would have nothing to offer), just not one that stops the LLM/fallback from
    producing a valid week in the first place.

    Warnings (candidate count > 0 but small, e.g. < 3) are worth surfacing but never gate on their
    own, since MP-020's AC is "non-zero", not a minimum margin.
    """
    blocking: list[str] = []
    non_blocking: list[str] = []
    warnings: list[str] = []
    with conn.cursor(row_factory=psycopg.rows.tuple_row) as cur:
        for item_type in ITEM_TYPES:
            suffix = _slot_suffix(item_type)
            target = blocking if item_type in ITEM_TYPE_TO_SLOTS else non_blocking
            for diet in VEG_OR_NONVEG:
                cur.execute(
                    "select dietary_flags from dishes where item_type = %s and veg_or_nonveg = %s",
                    (item_type, diet),
                )
                flag_sets = [frozenset(row[0]) for row in cur.fetchall()]

                if not flag_sets:
                    target.append(f"{item_type} / {diet}: 0 candidates unfiltered{suffix}")
                    continue  # no point checking exclusions on an already-empty group
                if len(flag_sets) < 3:
                    warnings.append(f"{item_type} / {diet}: only {len(flag_sets)} candidate(s) unfiltered")

                for subset in _minimal_failing_flag_sets(flag_sets):
                    label = " + ".join(sorted(subset))
                    target.append(f"{item_type} / {diet}, excluding [{label}]: 0 candidates{suffix}")
    return blocking, non_blocking, warnings


def main() -> int:
    conn = _connect()
    try:
        blocking, non_blocking, warnings = validate(conn)
    finally:
        conn.close()

    print(
        f"Checked {len(ITEM_TYPES) * len(VEG_OR_NONVEG)} (item_type, veg_or_nonveg) groups against "
        f"every combination of the {len(DIETARY_FLAGS)}-flag vocabulary a user could exclude "
        f"simultaneously, cross-referenced against {len(SLOT_ITEM_TYPES)} known slot/combo "
        "templates (version1_mealPlanner_technical.md §5 / _functionalities.md, see this script's "
        "own SLOT_ITEM_TYPES for exactly what's verbatim vs. inferred)."
    )

    if warnings:
        print(f"\n{len(warnings)} low-margin warning(s) (non-zero but thin — not a gate failure):")
        for w in warnings:
            print(f"  - {w}")

    if non_blocking:
        print(
            f"\n{len(non_blocking)} zero-candidate gap(s) NOT required by any known slot template "
            "(edit-time-only impact — does not block MP-034's core generation):"
        )
        for g in non_blocking:
            print(f"  - {g}")

    if blocking:
        print(f"\n{len(blocking)} BLOCKING ZERO-CANDIDATE GAP(S) — MP-020 gate FAILS:")
        for g in blocking:
            print(f"  - {g}")
        print(
            "\nEach of these needs a decision: source more dishes from the master catalogue's "
            "remaining rows (MP-003's fallback), relax which combination is required, or accept "
            "the gap for now — not something this script should silently work around."
        )
        return 1

    print("\nNo BLOCKING zero-candidate gaps. MP-020 gate PASSES (non-blocking gaps, if any, are listed above).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
