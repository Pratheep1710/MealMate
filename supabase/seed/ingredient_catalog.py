"""MP-016: canonical ingredient list, aliases, and staple/produce classification.

Extends the ~30 ingredients dev_placeholder_dishes.sql already seeded (kept, not duplicated —
`seed_ingredients` upserts on `canonical_name`, same as that file's own `on conflict ... do
nothing`) with the rest of the vocabulary that actually recurs across the master catalogue's Main
Ingredient(s) column, plus the Tamil-English alias pairs the catalogue's own text uses
interchangeably (e.g. "vengaya"/"onion", "kozhi"/"chicken" — several of these already do double
duty as catalog_taxonomy.py's dietary-flag/meat-type keywords; this is the canonical-identity side
of the same vocabulary, not a separate one).

Not claimed exhaustive: the workbook's Main Ingredient(s) column has ~390 distinct free-text
tokens, most single-occurrence regional/dish-specific phrasing that doesn't generalize into a
reusable canonical ingredient. This covers the recurring, genuinely reusable set — extensible, not
a one-time-complete taxonomy.

`is_staple` mirrors ingredients.is_staple's own meaning (0001: "excluded from grocery-photo
matching") — pantry items assumed always on hand, not something a grocery-availability check should
ask about.
"""

from __future__ import annotations

import os
import sys

import psycopg

# (canonical_name, is_staple) — canonical_name matches the lowercase, singular-ish convention
# already established by dev_placeholder_dishes.sql's ingredient pool.
CANONICAL_INGREDIENTS: tuple[tuple[str, bool], ...] = (
    # Staples already seeded by dev_placeholder_dishes.sql, repeated here so this module is a
    # complete, standalone source of truth — `on conflict (canonical_name) do nothing` makes
    # re-listing them harmless.
    ("rice", True),
    ("toor dal", True),
    ("moong dal", True),
    ("urad dal", True),
    ("chana dal", True),
    ("tamarind", True),
    ("mustard seeds", True),
    ("curry leaves", True),
    ("turmeric", True),
    ("chili powder", True),
    ("salt", True),
    ("oil", True),
    ("ghee", True),
    ("asafoetida", True),
    ("cardamom", True),
    ("jaggery", True),
    ("peanuts", True),
    # New staples/pantry — spices, lentils, millets used repeatedly across the catalogue.
    ("pepper", True),
    ("cumin", True),
    ("fennel seeds", True),
    ("coriander seeds", True),
    ("coriander leaves", True),
    ("mint", True),
    ("sesame seeds", True),
    ("horse gram", True),
    ("semolina", True),
    ("rice flour", True),
    ("pearl millet", True),
    ("finger millet", True),
    ("foxtail millet", True),
    ("barnyard millet", True),
    ("wheat flour", True),
    ("palm jaggery", True),
    ("cashew", True),
    ("almond", True),
    ("poppy seeds", True),
    # Non-staple produce/protein — the whole point of `is_staple=false` is that a grocery-photo
    # check should still ask about these.
    ("onion", False),
    ("tomato", False),
    ("garlic", False),
    ("coconut", False),
    ("semiya", False),
    ("milk", False),
    ("chicken", False),
    ("fish", False),
    ("cabbage", False),
    ("carrot", False),
    ("beans", False),
    ("curd", False),
    ("lemon", False),
    ("mutton", False),
    ("egg", False),
    ("prawn", False),
    ("crab", False),
    ("squid", False),
    ("brinjal", False),
    ("drumstick", False),
    ("okra", False),
    ("beetroot", False),
    ("radish", False),
    ("raw banana", False),
    ("banana stem", False),
    ("banana flower", False),
    ("moringa leaves", False),
    ("bitter gourd", False),
    ("ridge gourd", False),
    ("bottle gourd", False),
    ("yellow pumpkin", False),
    ("chayote", False),
    ("capsicum", False),
    ("colocasia", False),
    ("field beans", False),
    ("broad beans", False),
    ("cluster beans", False),
    ("paneer", False),
    ("butter", False),
    ("gooseberry", False),
)

# alias_text -> canonical_name. Every value here must be a name in CANONICAL_INGREDIENTS above —
# checked by test_ingredient_catalog.py, not just assumed.
ALIASES: dict[str, str] = {
    # Tamil produce/staple terms the catalogue's Main Ingredient(s)/Specific Dish Variety columns
    # use interchangeably with English.
    "vengaya": "onion",
    "poondu": "garlic",
    "thakkali": "tomato",
    "milagu": "pepper",
    "kothamalli": "coriander leaves",
    "pudhina": "mint",
    "ellu": "sesame seeds",
    "gingelly": "sesame seeds",
    "til": "sesame seeds",
    "kadalai": "peanuts",
    "nellikkai": "gooseberry",
    "karuveppilai": "curry leaves",
    # atta (whole wheat) and maida (refined) are distinct flours in practice but both map to one
    # canonical "wheat flour" at this taxonomy's granularity — same simplification the schema
    # already makes for e.g. veg_or_nonveg collapsing "Egg" into a binary field.
    "godhuma": "wheat flour",
    "atta": "wheat flour",
    "maida": "wheat flour",
    "rava": "semolina",
    "paal": "milk",
    "thair": "curd",
    "yogurt": "curd",  # not a separate canonical ingredient — same thing, culturally interchangeable
    # Tamil protein terms.
    "kozhi": "chicken",
    "nattukozhi": "chicken",
    "meen": "fish",
    "nethili": "fish",
    "sardine": "fish",
    "anchovy": "fish",
    "goat": "mutton",
    "muttai": "egg",
    "eral": "prawn",
    "shrimp": "prawn",
    "nandu": "crab",
    "kanava": "squid",
}


def seed_ingredients(conn: psycopg.Connection) -> tuple[int, int]:
    """Upserts CANONICAL_INGREDIENTS and ALIASES. Idempotent: `on conflict do nothing` on both
    (canonical_name is already unique per 0001; alias_text is the ingredient_aliases primary key),
    so re-running never duplicates or errors — same AC as MP-018's dish ingestion.

    Returns (ingredients_inserted, aliases_inserted); rows that already existed are silently
    no-ops, not counted as failures. Counted by before/after table size rather than
    cursor.rowcount, which psycopg3 doesn't reliably report per-row for `executemany` batches.
    """
    # Explicit tuple_row regardless of the connection's own row_factory — see ingest_catalog.py's
    # ingest() for why this matters (test fixtures in this repo default connections to dict_row).
    with conn.cursor(row_factory=psycopg.rows.tuple_row) as cur:
        ingredients_before = cur.execute("select count(*) from ingredients").fetchone()[0]
        aliases_before = cur.execute("select count(*) from ingredient_aliases").fetchone()[0]

        cur.executemany(
            "insert into ingredients (canonical_name, is_staple) values (%s, %s) "
            "on conflict (canonical_name) do nothing",
            CANONICAL_INGREDIENTS,
        )
        for alias_text, canonical_name in ALIASES.items():
            cur.execute(
                """
                insert into ingredient_aliases (alias_text, ingredient_id)
                select %s, id from ingredients where canonical_name = %s
                on conflict (alias_text) do nothing
                """,
                (alias_text, canonical_name),
            )

        ingredients_after = cur.execute("select count(*) from ingredients").fetchone()[0]
        aliases_after = cur.execute("select count(*) from ingredient_aliases").fetchone()[0]

    conn.commit()
    return ingredients_after - ingredients_before, aliases_after - aliases_before


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


def main() -> int:
    conn = _connect()
    try:
        inserted_ingredients, inserted_aliases = seed_ingredients(conn)
    except Exception as exc:
        conn.rollback()
        print("FAILED — rolled back, database unchanged.", file=sys.stderr)
        print(f"  {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"{inserted_ingredients} new ingredients, {inserted_aliases} new aliases.")
    print(f"({len(CANONICAL_INGREDIENTS)} canonical ingredients, {len(ALIASES)} aliases total in this module.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
