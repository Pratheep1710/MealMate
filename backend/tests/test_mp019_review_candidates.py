"""MP-019: unit tests for supabase/seed/mp019_review_candidates.py's grouping heuristics — pure
functions, no database or workbook needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SEED_DIR = Path(__file__).resolve().parents[2] / "supabase" / "seed"
if str(_SEED_DIR) not in sys.path:
    sys.path.insert(0, str(_SEED_DIR))

import mp019_review_candidates as mp019  # noqa: E402


class TestFindNearDuplicates:
    def test_regional_variants_of_the_same_base_dish_are_grouped(self) -> None:
        rows = [("Chettinad Kozhi Kuzhambu", "gravy"), ("Kongunadu Kozhi Kuzhambu", "gravy")]

        dupes = mp019.find_near_duplicates(rows)

        assert len(dupes) == 1
        (group,) = dupes.values()
        assert set(group) == {"Chettinad Kozhi Kuzhambu", "Kongunadu Kozhi Kuzhambu"}

    def test_different_item_types_are_never_grouped_together(self) -> None:
        rows = [("Lemon Rice", "rice"), ("Lemon Rice", "snack")]

        dupes = mp019.find_near_duplicates(rows)

        assert dupes == {}

    def test_genuinely_distinct_dishes_are_not_grouped(self) -> None:
        rows = [("Idli", "tiffin"), ("Dosa", "tiffin"), ("Pongal", "tiffin")]

        dupes = mp019.find_near_duplicates(rows)

        assert dupes == {}


class TestFindGenericSourced:
    def test_a_generic_south_indian_url_is_flagged(self) -> None:
        rows = [("Chicken 65", "https://example.com/collection/south-indian-non-veg-recipes")]

        flagged = mp019.find_generic_sourced(rows)

        assert flagged == [("Chicken 65", rows[0][1])]

    def test_a_tamil_specific_url_is_not_flagged_even_if_it_says_south_indian(self) -> None:
        rows = [("Idli", "https://example.com/tamil-south-indian-breakfast")]

        flagged = mp019.find_generic_sourced(rows)

        assert flagged == []

    def test_a_non_south_indian_url_is_not_flagged(self) -> None:
        rows = [("Idli", "https://en.wikipedia.org/wiki/Tamil_cuisine")]

        flagged = mp019.find_generic_sourced(rows)

        assert flagged == []

    def test_a_missing_url_is_skipped_not_flagged(self) -> None:
        rows = [("Mystery Dish", None)]

        flagged = mp019.find_generic_sourced(rows)

        assert flagged == []
