"""MP-016: tests for supabase/seed/ingredient_catalog.py — canonical ingredients, aliases, and
staple classification.
"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg
import pytest

_SEED_DIR = Path(__file__).resolve().parents[2] / "supabase" / "seed"
if str(_SEED_DIR) not in sys.path:
    sys.path.insert(0, str(_SEED_DIR))

import ingredient_catalog  # noqa: E402


class TestDataIntegrity:
    """Pure data checks — no database needed. These are the actual MP-016 AC: "ingredient aliases
    resolve to exactly one canonical ID" only holds if every alias target genuinely exists.
    """

    def test_every_alias_target_is_a_real_canonical_ingredient(self) -> None:
        canonical_names = {name for name, _ in ingredient_catalog.CANONICAL_INGREDIENTS}
        bad = {
            alias: target
            for alias, target in ingredient_catalog.ALIASES.items()
            if target not in canonical_names
        }
        assert bad == {}, f"aliases pointing at a non-existent canonical ingredient: {bad}"

    def test_canonical_names_have_no_duplicates(self) -> None:
        names = [name for name, _ in ingredient_catalog.CANONICAL_INGREDIENTS]
        assert len(names) == len(set(names))

    def test_no_alias_shadows_a_canonical_name_with_a_different_target(self) -> None:
        # An alias_text that's itself also a canonical_name would be ambiguous — which one does
        # "resolve" mean? Fine if it points at itself (redundant but harmless), not fine otherwise.
        canonical_names = {name for name, _ in ingredient_catalog.CANONICAL_INGREDIENTS}
        conflicts = {
            alias: target
            for alias, target in ingredient_catalog.ALIASES.items()
            if alias in canonical_names and target != alias
        }
        assert conflicts == {}, f"alias shadows a distinct canonical ingredient: {conflicts}"

    def test_every_alias_resolves_to_exactly_one_canonical_id_in_practice(self) -> None:
        # dict keys are inherently unique, but this is the actual AC stated in prose — assert it
        # against the real data shape rather than trusting "it's a dict" as a substitute.
        seen: dict[str, str] = {}
        for alias, target in ingredient_catalog.ALIASES.items():
            assert alias not in seen
            seen[alias] = target


class TestSeedIngredients:
    @pytest.fixture
    def clean_catalog(self, conn: psycopg.Connection):
        # See test_ingest_catalog.py's clean_dishes fixture for why this commits its own cleanup —
        # pg_dsn is a session-scoped database shared with every other test file.
        conn.execute("delete from ingredient_aliases")
        conn.execute("delete from ingredients")
        conn.commit()
        yield
        conn.execute("delete from ingredient_aliases")
        conn.execute("delete from ingredients")
        conn.commit()

    def test_seeding_is_idempotent(self, conn, clean_catalog) -> None:
        first_ingredients, first_aliases = ingredient_catalog.seed_ingredients(conn)
        assert first_ingredients == len(ingredient_catalog.CANONICAL_INGREDIENTS)
        assert first_aliases == len(ingredient_catalog.ALIASES)

        second_ingredients, second_aliases = ingredient_catalog.seed_ingredients(conn)
        assert (second_ingredients, second_aliases) == (0, 0)

        total = conn.execute("select count(*) as n from ingredients").fetchone()["n"]
        assert total == len(ingredient_catalog.CANONICAL_INGREDIENTS)

    def test_an_alias_resolves_to_its_canonical_ingredient(self, conn, clean_catalog) -> None:
        ingredient_catalog.seed_ingredients(conn)

        row = conn.execute(
            """
            select i.canonical_name, i.is_staple
            from ingredient_aliases a
            join ingredients i on i.id = a.ingredient_id
            where a.alias_text = 'vengaya'
            """
        ).fetchone()

        assert row["canonical_name"] == "onion"
        assert row["is_staple"] is False

    def test_staples_are_tagged_explicitly(self, conn, clean_catalog) -> None:
        ingredient_catalog.seed_ingredients(conn)

        row = conn.execute(
            "select is_staple from ingredients where canonical_name = 'rice'"
        ).fetchone()
        assert row["is_staple"] is True
