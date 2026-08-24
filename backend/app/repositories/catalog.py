"""MP-031: candidate catalog queries (dishes/ingredients) — read-only; catalog tables are
populated only by the MP-018 ingestion job (blocked pending the dish workbook as of Phase 2,
see docs/MP-015-catalog-blocked.md), never written here.
"""

from __future__ import annotations

import uuid

import psycopg
from psycopg.rows import DictRow

from app.models import Dish, Ingredient

_DISH_COLUMNS = (
    "id, name, item_type, veg_or_nonveg, region_style, prep_minutes, track_variety, dietary_flags"
)


def get_candidates(
    conn: psycopg.Connection[DictRow],
    *,
    item_type: str,
    veg_or_nonveg: str | None = None,
    exclude_dietary_flags: list[str] | None = None,
    exclude_dish_ids: list[uuid.UUID] | None = None,
) -> list[Dish]:
    """Candidate-filtered dish lookup — the read path MP-034's generation engine will build on.
    `exclude_dietary_flags` is a hard exclusion (array-overlap test): any dish carrying even one
    of the given flags is dropped, matching MP-017's hard-exclusion intent.
    """
    conditions = ["item_type = %s"]
    params: list[object] = [item_type]
    if veg_or_nonveg is not None:
        conditions.append("veg_or_nonveg = %s")
        params.append(veg_or_nonveg)
    if exclude_dietary_flags:
        conditions.append("not (dietary_flags && %s)")
        params.append(exclude_dietary_flags)
    if exclude_dish_ids:
        conditions.append("id <> all(%s)")
        params.append(exclude_dish_ids)
    sql = f"select {_DISH_COLUMNS} from dishes where " + " and ".join(conditions)
    rows = conn.execute(sql, params).fetchall()
    return [Dish.model_validate(row) for row in rows]


def get_ingredients_for_dish(
    conn: psycopg.Connection[DictRow], dish_id: uuid.UUID
) -> list[Ingredient]:
    rows = conn.execute(
        """
        select i.id, i.canonical_name, i.is_staple
        from dish_ingredients di
        join ingredients i on i.id = di.ingredient_id
        where di.dish_id = %s
        """,
        (dish_id,),
    ).fetchall()
    return [Ingredient.model_validate(row) for row in rows]


def resolve_ingredient_alias(
    conn: psycopg.Connection[DictRow], alias_text: str
) -> Ingredient | None:
    row = conn.execute(
        """
        select i.id, i.canonical_name, i.is_staple
        from ingredient_aliases a
        join ingredients i on i.id = a.ingredient_id
        where a.alias_text = %s
        """,
        (alias_text,),
    ).fetchone()
    return Ingredient.model_validate(row) if row else None
