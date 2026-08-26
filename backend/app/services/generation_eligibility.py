"""Shared hard-eligibility policy for generated and fallback dish selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models import Dish
from app.models.dish import DIETARY_FLAG_VALUES

if TYPE_CHECKING:
    from app.services.generation_context import GenerationContext


def normalized_dietary_flags(dish: Dish) -> frozenset[str] | None:
    """Return validated flags, or ``None`` when safety metadata is absent or malformed."""
    raw_flags = getattr(dish, "dietary_flags", None)
    if raw_flags is None or not isinstance(raw_flags, list):
        return None
    flags = frozenset(raw_flags)
    if any(flag not in DIETARY_FLAG_VALUES for flag in flags):
        return None
    return flags


def dietary_conflicts(dish: Dish, restrictions: list[str]) -> frozenset[str]:
    flags = normalized_dietary_flags(dish)
    return frozenset() if flags is None else flags & frozenset(restrictions)


def is_eligible(dish: Dish, context: GenerationContext) -> bool:
    """The single hard gate shared by response validation and fallback selection."""
    flags = normalized_dietary_flags(dish)
    return (
        dish.id in context.eligible_dish_ids
        and flags is not None
        and not (flags & frozenset(context.profile.dietary_restrictions))
    )
