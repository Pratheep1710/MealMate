"""MP-031: meal_plans / plan_items / grocery_list_snapshot — the weekly plan artifacts.

meal_plans/plan_items rows are written by the generation job (service_role) and by the
client-facing edit path (swap/add/remove, docs/MP-001 "Weekly review/edit"); grocery_list_snapshot
is frozen at "week ready" time by the generation job only (docs/MP-001 "Grocery list").
"""

from __future__ import annotations

import dataclasses
import datetime
import uuid
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import DictRow
from psycopg.types.json import Json

from app.models import GroceryListSnapshot, MealPlan, PlanItem

_PLAN_COLUMNS = "id, user_id, plan_date, slot, is_skipped, created_at"
_ITEM_COLUMNS = "id, plan_id, item_type, dish_id, status, make_extra"
_SNAPSHOT_COLUMNS = "user_id, week_start, ingredients, created_at"


@dataclasses.dataclass(frozen=True)
class DaySlotSummary:
    """A read-shape for MP-070's reminder copy — not a table mirror (see app/models/__init__.py's
    one-class-per-table convention), so it lives here rather than in app/models.
    """

    slot: str
    is_skipped: bool
    dish_names: list[str]


@dataclasses.dataclass(frozen=True)
class GroceryIngredientRow:
    ingredient_id: uuid.UUID
    name: str
    is_staple: bool
    quantity: Decimal | None
    unit: str | None


def get_week_plan(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, week_start: datetime.date
) -> list[MealPlan]:
    week_end = week_start + datetime.timedelta(days=6)
    rows = conn.execute(
        f"""
        select {_PLAN_COLUMNS} from meal_plans
        where user_id = %s and plan_date between %s and %s
        order by plan_date, slot
        """,
        (user_id, week_start, week_end),
    ).fetchall()
    return [MealPlan.model_validate(row) for row in rows]


def get_day_plan_with_dishes(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, plan_date: datetime.date
) -> list[DaySlotSummary]:
    """One row per slot for `plan_date`, each carrying the dish name(s) currently filled in —
    reflecting whatever the user has edited/skipped since generation, since there is only ever one
    live `meal_plans`/`plan_items` row (docs/MP-001: "every edit autosaves and is immediately
    live"). MP-070's reminder job reads this the evening before, not a frozen generation-time copy.
    """
    rows = conn.execute(
        """
        select mp.slot, mp.is_skipped, d.name as dish_name
        from meal_plans mp
        left join plan_items pi on pi.plan_id = mp.id and pi.status = 'filled'
        left join dishes d on d.id = pi.dish_id
        where mp.user_id = %s and mp.plan_date = %s
        order by mp.slot
        """,
        (user_id, plan_date),
    ).fetchall()

    by_slot: dict[str, DaySlotSummary] = {}
    for row in rows:
        slot = row["slot"]
        if slot not in by_slot:
            by_slot[slot] = DaySlotSummary(slot=slot, is_skipped=row["is_skipped"], dish_names=[])
        if row["dish_name"]:
            by_slot[slot].dish_names.append(row["dish_name"])
    return list(by_slot.values())


def create_plan_day(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, plan_date: datetime.date, slot: str
) -> MealPlan:
    row = conn.execute(
        f"""
        insert into meal_plans (user_id, plan_date, slot)
        values (%s, %s, %s)
        on conflict (user_id, plan_date, slot) do update set slot = excluded.slot
        returning {_PLAN_COLUMNS}
        """,
        (user_id, plan_date, slot),
    ).fetchone()
    assert row is not None
    return MealPlan.model_validate(row)


def set_plan_skipped(
    conn: psycopg.Connection[DictRow], plan_id: uuid.UUID, is_skipped: bool
) -> MealPlan:
    """Docs/MP-001's skip/eating-out toggle: drops the day/slot from the grocery list and from
    variety/history tracking (app/repositories/history.py filters on this column).
    """
    row = conn.execute(
        f"update meal_plans set is_skipped = %s where id = %s returning {_PLAN_COLUMNS}",
        (is_skipped, plan_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"meal_plans row {plan_id} not found")
    return MealPlan.model_validate(row)


def get_plan_items(conn: psycopg.Connection[DictRow], plan_id: uuid.UUID) -> list[PlanItem]:
    rows = conn.execute(
        f"select {_ITEM_COLUMNS} from plan_items where plan_id = %s", (plan_id,)
    ).fetchall()
    return [PlanItem.model_validate(row) for row in rows]


def clear_plan_items_for_dates(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    plan_dates: list[datetime.date],
) -> None:
    """Clears only regenerated dates, preserving earlier days in a partial-week replan."""
    if not plan_dates:
        return
    conn.execute(
        """
        delete from plan_items pi
        using meal_plans mp
        where pi.plan_id = mp.id
          and mp.user_id = %s
          and mp.plan_date = any(%s)
        """,
        (user_id, plan_dates),
    )
    conn.execute(
        """
        update meal_plans
        set is_skipped = false
        where user_id = %s and plan_date = any(%s)
        """,
        (user_id, plan_dates),
    )


def get_grocery_ingredient_rows(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    plan_dates: list[datetime.date],
) -> list[GroceryIngredientRow]:
    """Ingredient occurrences for exactly the dates being snapshotted."""
    if not plan_dates:
        return []
    rows = conn.execute(
        """
        select i.id as ingredient_id, i.canonical_name as name, i.is_staple,
               di.quantity, di.unit
        from meal_plans mp
        join plan_items pi on pi.plan_id = mp.id
        join dish_ingredients di on di.dish_id = pi.dish_id
        join ingredients i on i.id = di.ingredient_id
        where mp.user_id = %s
          and mp.plan_date = any(%s)
          and mp.is_skipped = false
          and pi.status = 'filled'
        order by i.canonical_name, i.id, di.unit nulls first
        """,
        (user_id, plan_dates),
    ).fetchall()
    return [GroceryIngredientRow(**row) for row in rows]


def add_plan_item(
    conn: psycopg.Connection[DictRow],
    plan_id: uuid.UUID,
    item_type: str,
    dish_id: uuid.UUID | None,
    make_extra: bool = False,
    *,
    status: str = "filled",
) -> PlanItem:
    """`status='needs_manual_pick'` (technical spec §5.1 step 5) is the fallback state for a
    (day, slot, item_type) with zero eligible candidates even after relaxing the 10-day rule —
    `dish_id` must be omitted for it, matching the `plan_items_dish_id_required_unless_manual_pick`
    DB constraint (0007). Resolve it later via `resolve_manual_pick`.
    """
    if status == "needs_manual_pick" and dish_id is not None:
        raise ValueError("needs_manual_pick items must not carry a dish_id")
    if status == "filled" and dish_id is None:
        raise ValueError("filled items must carry a dish_id")
    row = conn.execute(
        f"""
        insert into plan_items (plan_id, item_type, dish_id, status, make_extra)
        values (%s, %s, %s, %s, %s)
        returning {_ITEM_COLUMNS}
        """,
        (plan_id, item_type, dish_id, status, make_extra),
    ).fetchone()
    assert row is not None
    return PlanItem.model_validate(row)


def resolve_manual_pick(
    conn: psycopg.Connection[DictRow], plan_item_id: uuid.UUID, dish_id: uuid.UUID
) -> PlanItem:
    """Moves a `needs_manual_pick` item to `filled` once the user (or a retry) picks a dish."""
    row = conn.execute(
        f"""
        update plan_items set dish_id = %s, status = 'filled'
        where id = %s
        returning {_ITEM_COLUMNS}
        """,
        (dish_id, plan_item_id),
    ).fetchone()
    if row is None:
        raise ValueError(f"plan_items row {plan_item_id} not found")
    return PlanItem.model_validate(row)


def remove_plan_item(conn: psycopg.Connection[DictRow], plan_item_id: uuid.UUID) -> None:
    conn.execute("delete from plan_items where id = %s", (plan_item_id,))


def get_grocery_snapshot(
    conn: psycopg.Connection[DictRow], user_id: uuid.UUID, week_start: datetime.date
) -> GroceryListSnapshot | None:
    row = conn.execute(
        f"select {_SNAPSHOT_COLUMNS} from grocery_list_snapshot "
        "where user_id = %s and week_start = %s",
        (user_id, week_start),
    ).fetchone()
    return GroceryListSnapshot.model_validate(row) if row else None


def write_grocery_snapshot(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    week_start: datetime.date,
    ingredients: list[dict[str, Any]],
) -> GroceryListSnapshot:
    row = conn.execute(
        f"""
        insert into grocery_list_snapshot (user_id, week_start, ingredients)
        values (%s, %s, %s)
        on conflict (user_id, week_start) do update set
            ingredients = excluded.ingredients,
            created_at = now()
        returning {_SNAPSHOT_COLUMNS}
        """,
        (user_id, week_start, Json(ingredients)),
    ).fetchone()
    assert row is not None
    return GroceryListSnapshot.model_validate(row)
