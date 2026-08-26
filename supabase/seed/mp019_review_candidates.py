"""MP-019: generates the human-review candidate list — near-duplicate names and dishes whose
source citation isn't Tamil-Nadu-specific. Produces a report only; never deletes or modifies a
row. The removal decision is explicitly human (Phase 5 brief §0/§2) — this script's only job is to
surface candidates so that judgment call doesn't have to start from a blank slate.

Two checks:
  1. Near-duplicate names: dishes in the same item_type whose name, after stripping common
     regional/style qualifiers ("Tamil style", "Chettinad", "Kongunadu", etc.), collapses to the
     same normalized text. Likely to include real regional variants (a Chettinad version and a
     Kongunadu version of the same base dish are both legitimate, not duplicates) alongside actual
     accidental repeats — the heuristic can't tell those apart, which is exactly why this is a
     candidate list for a human, not an auto-dedup.
  2. Non-Tamil-Nadu-specific sourcing: rows whose workbook Source URL is a generic "South Indian"
     collection rather than a Tamil-Nadu-specific one, per MP-003's regional gate ("reject
     anything only generically South Indian"). Flagged for citation review, not necessarily
     removal — see the note printed with each group.

Usage:
  python supabase/seed/mp019_review_candidates.py path/to/Tamil_Nadu_Dishes_Master_Catalogue_Claude.xlsx
"""

from __future__ import annotations

import collections
import re
import sys

import openpyxl

_REGIONAL_QUALIFIERS = re.compile(
    r"\b(tamil style|tamil nadu style|tamil nadu|style|kongunadu|chettinad|karaikudi|madurai|"
    r"dindigul|nanjil nadu)\b"
)


def _normalize(name: str) -> str:
    n = _REGIONAL_QUALIFIERS.sub("", name.lower())
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def find_near_duplicates(rows: list[tuple]) -> dict[tuple[str, str], list[str]]:
    """rows: (name, item_type) pairs. Groups by (item_type, normalized-name)."""
    groups: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for name, item_type in rows:
        groups[(item_type, _normalize(name))].append(name)
    return {k: v for k, v in groups.items() if len(v) > 1}


def find_generic_sourced(rows: list[tuple]) -> list[tuple[str, str]]:
    """rows: (name, source_url) pairs. Flags URLs whose path reads as "south indian" rather than
    Tamil-Nadu-specific — a citation-specificity check, not a claim the dish itself is foreign.
    """
    return [
        (name, url)
        for name, url in rows
        if url and "south-indian" in url.lower() and "tamil" not in url.lower()
    ]


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python mp019_review_candidates.py path/to/workbook.xlsx", file=sys.stderr)
        return 1

    wb = openpyxl.load_workbook(sys.argv[1], read_only=True, data_only=True)
    ws = wb["Master Dishes"]
    all_rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if r and any(r)]

    dup_input = [(r[5], r[3]) for r in all_rows if r[5]]
    dupes = find_near_duplicates(dup_input)

    source_input = [(r[5], r[12]) for r in all_rows if r[5]]
    generic_sourced = find_generic_sourced(source_input)

    print(f"{len(all_rows)} total rows in the workbook.\n")

    print(f"== Near-duplicate name candidates ({len(dupes)} group(s)) ==")
    print("Likely includes legitimate regional variants alongside real duplicates — review each")
    print("group; a Chettinad and a Kongunadu version of the same base dish are not duplicates.\n")
    for (item_type, _norm), names in sorted(dupes.items()):
        print(f"  [{item_type}] " + " / ".join(names))

    print(f"\n== Generically-sourced candidates ({len(generic_sourced)} row(s)) ==")
    print("Source URL reads as a generic 'South Indian' collection rather than Tamil-Nadu-")
    print("specific (MP-003's regional gate). Most of these are still clearly Tamil-coded by name")
    print("(Chettinad/Kongunadu prefixes, Tamil terms) — this flags a citation-specificity gap,")
    print("not a claim that the dish itself isn't Tamil Nadu cuisine. Review and either accept the")
    print("citation, find a more specific source, or remove.\n")
    for name, url in generic_sourced:
        print(f"  - {name}  ({url})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
