"""MP-020: tests for supabase/seed/validate_coverage.py's coverage matrix logic, against a real
throwaway database (conftest.py's `conn`/`pg_dsn` fixtures).
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest

_SEED_DIR = Path(__file__).resolve().parents[2] / "supabase" / "seed"
if str(_SEED_DIR) not in sys.path:
    sys.path.insert(0, str(_SEED_DIR))

import validate_coverage  # noqa: E402


@pytest.fixture
def clean_dishes(conn: psycopg.Connection):
    conn.execute("delete from dishes")
    conn.commit()
    yield
    conn.execute("delete from dishes")
    conn.commit()


def _insert(
    conn: psycopg.Connection, *, item_type: str, veg_or_nonveg: str, flags: list[str] | None = None
) -> None:
    flags = flags or []
    name = f"Test {item_type} {veg_or_nonveg} {flags}-{id(object())}"
    conn.execute(
        "insert into dishes (name, item_type, veg_or_nonveg, dietary_flags) "
        "values (%s, %s, %s, %s)",
        (name, item_type, veg_or_nonveg, flags),
    )


class TestMinimalFailingFlagSets:
    """Pure logic, no database — the combinatorics are the part worth testing precisely."""

    def test_an_empty_group_returns_no_minimal_sets(self) -> None:
        # The caller handles a fully-empty group as its own top-level gap, not via this function.
        assert validate_coverage._minimal_failing_flag_sets([]) == []

    def test_a_dish_with_no_flags_means_nothing_fails(self) -> None:
        result = validate_coverage._minimal_failing_flag_sets([frozenset()])
        assert result == []

    def test_a_single_flag_shared_by_every_dish_is_a_minimal_failure(self) -> None:
        flag_sets = [frozenset({"Seafood"}), frozenset({"Seafood", "Egg"})]

        result = validate_coverage._minimal_failing_flag_sets(
            flag_sets, all_flags=("Seafood", "Egg")
        )

        assert result == [frozenset({"Seafood"})]

    def test_two_flags_together_can_fail_even_though_neither_alone_does(self) -> None:
        # One dish is safe unless BOTH Gluten and Nuts are excluded together — the reviewer's exact
        # example: passes every single-flag check, fails the simultaneous combination.
        flag_sets = [frozenset({"Gluten"}), frozenset({"Nuts"})]

        result = validate_coverage._minimal_failing_flag_sets(
            flag_sets, all_flags=("Gluten", "Nuts")
        )

        assert result == [frozenset({"Gluten", "Nuts"})]

    def test_a_superset_of_an_already_failing_set_is_not_reported_separately(self) -> None:
        # Every dish contains Gluten, so {Gluten} alone already fails — {Gluten, Nuts} and every
        # other superset containing Gluten are trivial consequences, not separately reported.
        flag_sets = [frozenset({"Gluten"}), frozenset({"Gluten", "Nuts"})]

        result = validate_coverage._minimal_failing_flag_sets(
            flag_sets, all_flags=("Gluten", "Nuts", "Egg")
        )

        assert result == [frozenset({"Gluten"})]


class TestValidate:
    def test_a_combination_with_zero_dishes_at_all_is_a_gap(self, conn, clean_dishes) -> None:
        # Nothing inserted at all — every combination should be a gap.
        gaps, _ = validate_coverage.validate(conn)

        assert len(gaps) > 0
        assert any("tiffin / veg" in g for g in gaps)

    def test_a_fully_covered_combination_produces_no_gap_for_it(self, conn, clean_dishes) -> None:
        # Cover just "sweet / veg" with a dish carrying no dietary flags, so every exclusion
        # combination still leaves it as a candidate.
        _insert(conn, item_type="sweet", veg_or_nonveg="veg", flags=[])
        conn.commit()

        gaps, _ = validate_coverage.validate(conn)

        assert not any(g.startswith("sweet / veg") for g in gaps)

    def test_a_dish_that_always_carries_one_flag_creates_a_gap_only_for_that_flags_exclusion(
        self, conn, clean_dishes
    ) -> None:
        # The only "gravy / nonveg" dish always contains Seafood — excluding Seafood empties that
        # combination, but the unfiltered count passes.
        _insert(conn, item_type="gravy", veg_or_nonveg="nonveg", flags=["Seafood"])
        conn.commit()

        gaps, _ = validate_coverage.validate(conn)

        assert any(g == "gravy / nonveg, excluding [Seafood]: 0 candidates" for g in gaps)
        assert not any(g.startswith("gravy / nonveg: 0 candidates unfiltered") for g in gaps)

    def test_a_simultaneous_two_flag_exclusion_is_caught_even_when_each_flag_alone_is_fine(
        self, conn, clean_dishes
    ) -> None:
        # One dish is Gluten-only, the other is Nuts-only — excluding either flag alone still
        # leaves the other dish standing, but excluding both together empties the group. This is
        # the PR #12 review's concrete example.
        _insert(conn, item_type="tiffin", veg_or_nonveg="veg", flags=["Gluten"])
        _insert(conn, item_type="tiffin", veg_or_nonveg="veg", flags=["Nuts"])
        conn.commit()

        gaps, _ = validate_coverage.validate(conn)

        assert not any(g == "tiffin / veg, excluding [Gluten]: 0 candidates" for g in gaps)
        assert not any(g == "tiffin / veg, excluding [Nuts]: 0 candidates" for g in gaps)
        assert any(g == "tiffin / veg, excluding [Gluten + Nuts]: 0 candidates" for g in gaps)

    def test_low_margin_warns_but_does_not_gate(self, conn, clean_dishes) -> None:
        _insert(conn, item_type="kootu", veg_or_nonveg="veg", flags=[])
        conn.commit()

        gaps, warnings = validate_coverage.validate(conn)

        assert not any(g.startswith("kootu / veg") for g in gaps)
        assert any("kootu / veg" in w for w in warnings)
