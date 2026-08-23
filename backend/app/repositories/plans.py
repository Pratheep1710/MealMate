"""MP-031: meal_plans / plan_items / grocery_list_snapshot — the weekly plan artifacts.

meal_plans/plan_items rows are written by the generation job (service_role) and by the
client-facing edit path (swap/add/remove, docs/MP-001 "Weekly review/edit"); grocery_list_snapshot
is frozen at "week ready" time by the generation job only (docs/MP-001 "Grocery list").
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import psycopg
from psycopg.rows import DictRow
from psycopg.types.json import Json

from app.models import GroceryListSnapshot, MealPlan, PlanItem

_PLAN_COLUMNS = "id, user_id, plan_date, slot, created_at"
_ITEM_COLUMNS = "id, plan_id, item_type, dish_id, make_extra, status"
_SNAPSHOT_COLUMNS = "user_id, week_start, ingredients, created_at"


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


def get_plan_items(conn: psycopg.Connection[DictRow], plan_id: uuid.UUID) -> list[PlanItem]:
    rows = conn.execute(
        f"select {_ITEM_COLUMNS} from plan_items where plan_id = %s", (plan_id,)
    ).fetchall()
    return [PlanItem.model_validate(row) for row in rows]


def add_plan_item(
    conn: psycopg.Connection[DictRow],
    plan_id: uuid.UUID,
    item_type: str,
    dish_id: uuid.UUID,
    make_extra: bool = False,
) -> PlanItem:
    row = conn.execute(
        f"""
        insert into plan_items (plan_id, item_type, dish_id, make_extra)
        values (%s, %s, %s, %s)
        returning {_ITEM_COLUMNS}
        """,
        (plan_id, item_type, dish_id, make_extra),
    ).fetchone()
    assert row is not None
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
        on conflict (user_id, week_start) do update set ingredients = excluded.ingredients
        returning {_SNAPSHOT_COLUMNS}
        """,
        (user_id, week_start, Json(ingredients)),
    ).fetchone()
    assert row is not None
    return GroceryListSnapshot.model_validate(row)
