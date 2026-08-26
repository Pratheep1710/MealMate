from __future__ import annotations

import uuid
from decimal import Decimal

from generation_test_helpers import make_context

from app.repositories.plans import GroceryIngredientRow
from app.services.plan_persistence import build_grocery_payload


def _row(
    ingredient_id: uuid.UUID,
    *,
    name: str = "Onion",
    quantity: Decimal | None = Decimal("1.5"),
    unit: str | None = "kg",
    is_staple: bool = False,
) -> GroceryIngredientRow:
    return GroceryIngredientRow(ingredient_id, name, is_staple, quantity, unit)


def test_suggestion_payload_aggregates_quantities_without_float_loss() -> None:
    context = make_context()
    ingredient_id = uuid.uuid4()
    payload = build_grocery_payload(
        [_row(ingredient_id), _row(ingredient_id, quantity=Decimal("0.25"))],
        context.profile,
        frozenset(),
    )
    assert payload == [
        {
            "ingredient_id": str(ingredient_id),
            "name": "Onion",
            "quantity": "1.75",
            "unit": "kg",
        }
    ]


def test_any_unknown_amount_keeps_the_aggregate_presence_only() -> None:
    context = make_context()
    ingredient_id = uuid.uuid4()
    payload = build_grocery_payload(
        [
            _row(ingredient_id),
            _row(ingredient_id, quantity=None, unit=None),
        ],
        context.profile,
        frozenset(),
    )
    assert {item["quantity"] for item in payload} == {"1.5", None}


def test_reserves_payload_excludes_available_items_and_staples() -> None:
    context = make_context(planning_mode="reserves")
    available_id = uuid.uuid4()
    staple_id = uuid.uuid4()
    missing_id = uuid.uuid4()
    payload = build_grocery_payload(
        [
            _row(available_id),
            _row(staple_id, name="Rice", is_staple=True),
            _row(missing_id, name="Tomato"),
        ],
        context.profile,
        frozenset({available_id}),
    )
    assert [item["ingredient_id"] for item in payload] == [str(missing_id)]
