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
  2. Non-Tamil-Nadu-specific sourcing: rows whose workbook Source URL doesn't read as
     Tamil-Nadu-specific, per MP-003's regional gate ("every selected dish traceable to a Tamil
     Nadu source... reject anything only generically South Indian"). PR #12 review finding: an
     earlier version only matched URLs literally containing "south-indian", silently skipping rows
     with no source URL at all — a missing citation is *worse* than a generic one for a
     traceability requirement, not something to ignore. Flags a row if its Source URL is missing,
     blank, or simply doesn't mention Tamil Nadu at all — flagged for citation review, not
     necessarily removal — see the note printed with each group.

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


def find_non_tamil_specific_sourced(rows: list[tuple]) -> list[tuple[str, str | None]]:
    """rows: (name, source_url) pairs. Flags a row if its source doesn't establish Tamil-Nadu
    traceability at all: missing/blank, or present but not mentioning Tamil Nadu — a
    citation-specificity/completeness check, not a claim the dish itself is foreign. A missing URL
    is flagged (not skipped): MP-003's regional gate is a traceability requirement, and "no
    citation" is a stronger failure of that than "generic citation".
    """
    flagged = []
    for name, url in rows:
        if not url or not str(url).strip():
            flagged.append((name, None))
        elif "tamil" not in str(url).lower():
            flagged.append((name, url))
    return flagged


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
    flagged_sources = find_non_tamil_specific_sourced(source_input)

    print(f"{len(all_rows)} total rows in the workbook.\n")

    print(f"== Near-duplicate name candidates ({len(dupes)} group(s)) ==")
    print("Likely includes legitimate regional variants alongside real duplicates — review each")
    print("group; a Chettinad and a Kongunadu version of the same base dish are not duplicates.\n")
    for (item_type, _norm), names in sorted(dupes.items()):
        print(f"  [{item_type}] " + " / ".join(names))

    missing = [n for n, u in flagged_sources if u is None]
    non_tamil = [(n, u) for n, u in flagged_sources if u is not None]
    print(f"\n== Sourcing candidates ({len(flagged_sources)} row(s)) ==")
    print("Rows whose Source URL doesn't establish Tamil-Nadu traceability (MP-003's regional")
    print("gate) — either missing entirely, or present but not mentioning Tamil Nadu. Most of the")
    print("latter are still clearly Tamil-coded by name (Chettinad/Kongunadu prefixes, Tamil")
    print("terms) — this flags a citation gap, not a claim the dish itself isn't Tamil Nadu")
    print("cuisine. Review and either accept, find a more specific source, or remove.\n")
    if missing:
        print(f"  -- {len(missing)} row(s) with NO source URL at all --")
        for name in missing:
            print(f"  - {name}  (no source URL)")
    if non_tamil:
        print(f"  -- {len(non_tamil)} row(s) with a source URL that doesn't mention Tamil Nadu --")
        for name, url in non_tamil:
            print(f"  - {name}  ({url})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
