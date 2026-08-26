"""Phase 6 atomic plan persistence and grocery snapshot construction."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import DictRow

from app.models import GroceryListSnapshot, MealPlan, NotificationLog, UserProfile
from app.repositories import notifications as notifications_repo
from app.repositories import plans as plans_repo
from app.services.generation_models import GeneratedPlan


@dataclass(frozen=True)
class PersistenceResult:
    snapshot: GroceryListSnapshot
    notification: NotificationLog


def _quantity_json(quantity: Decimal | None) -> str | None:
    return format(quantity, "f") if quantity is not None else None


def build_grocery_payload(
    rows: list[plans_repo.GroceryIngredientRow],
    profile: UserProfile,
    available_ingredient_ids: frozenset[uuid.UUID],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[uuid.UUID, str | None], dict[str, Any]] = {}
    for row in rows:
        if profile.planning_mode == "reserves" and (
            row.is_staple or row.ingredient_id in available_ingredient_ids
        ):
            continue
        key = (row.ingredient_id, row.unit)
        entry = grouped.setdefault(
            key,
            {
                "ingredient_id": str(row.ingredient_id),
                "name": row.name,
                "quantity": Decimal(0),
                "unit": row.unit,
                "has_unknown_quantity": False,
            },
        )
        if row.quantity is None:
            entry["has_unknown_quantity"] = True
        else:
            entry["quantity"] += row.quantity

    payload: list[dict[str, Any]] = []
    for entry in grouped.values():
        payload.append(
            {
                "ingredient_id": entry["ingredient_id"],
                "name": entry["name"],
                "quantity": None
                if entry["has_unknown_quantity"]
                else _quantity_json(entry["quantity"]),
                "unit": entry["unit"],
            }
        )
    return sorted(payload, key=lambda item: (str(item["name"]).casefold(), str(item["unit"])))


def persist_generated_plan(
    conn: psycopg.Connection[DictRow],
    user_id: uuid.UUID,
    profile: UserProfile,
    plan: GeneratedPlan,
    available_ingredient_ids: frozenset[uuid.UUID],
) -> PersistenceResult:
    target_dates = sorted({item.day for item in plan.items})
    plans_repo.clear_plan_items_for_dates(conn, user_id, target_dates)

    plans_by_key: dict[tuple[datetime.date, str], MealPlan] = {}
    for item in plan.items:
        key = (item.day, item.slot)
        meal_plan = plans_by_key.get(key)
        if meal_plan is None:
            meal_plan = plans_repo.create_plan_day(conn, user_id, item.day, item.slot)
            plans_by_key[key] = meal_plan
        plans_repo.add_plan_item(
            conn,
            meal_plan.id,
            item.item_type,
            item.dish_id,
            status=item.status,
        )

    rows = plans_repo.get_grocery_ingredient_rows(conn, user_id, target_dates)
    payload = build_grocery_payload(rows, profile, available_ingredient_ids)
    snapshot = plans_repo.write_grocery_snapshot(conn, user_id, plan.week_start, payload)
    notification = notifications_repo.upsert_pending(conn, user_id, "week_ready", plan.week_start)
    return PersistenceResult(snapshot=snapshot, notification=notification)
