"""Technical spec section 5.1 deterministic rule-based fallback."""

from __future__ import annotations

import datetime
import uuid

from app.models import Dish
from app.services.generation_context import GenerationContext
from app.services.generation_models import GeneratedPlan, PlannedItem


def _rank(dish: Dish, context: GenerationContext, *, quick: bool) -> tuple[object, ...]:
    return (
        0 if dish.id in context.favorite_dish_ids else 1,
        context.last_used_by_dish_id.get(dish.id, datetime.date.min),
        dish.prep_minutes if quick and dish.prep_minutes is not None else 10**9 if quick else 0,
        dish.name.casefold(),
        str(dish.id),
    )


def _pick(
    context: GenerationContext,
    *,
    item_type: str,
    desired_diet: str | None,
    used_variety_ids: set[uuid.UUID],
    quick: bool,
) -> Dish | None:
    restrictions = set(context.profile.dietary_restrictions)
    group = next((group for group in context.catalog if group.item_type == item_type), None)
    candidates = [
        dish
        for dish in (group.dishes if group else ())
        if dish.id in context.eligible_dish_ids
        and not (set(dish.dietary_flags) & restrictions)
        and (not dish.track_variety or dish.id not in used_variety_ids)
        and (desired_diet is None or dish.veg_or_nonveg == desired_diet)
    ]
    strict = [dish for dish in candidates if dish.id not in context.recent_dish_ids]
    eligible = strict or candidates  # relax trailing history before any other soft constraint
    return min(eligible, key=lambda dish: _rank(dish, context, quick=quick)) if eligible else None


def build_fallback_plan(context: GenerationContext) -> GeneratedPlan:
    """Choose one minimum-count item per template requirement, never relaxing safety.

    Dietary restrictions, Reserves eligibility, and in-week variety are hard. History is relaxed
    first when a pool empties. Non-veg placement is attempted on each target date but may relax to
    the other diet rather than leaving an otherwise fillable slot blank. A truly empty safe pool
    becomes ``needs_manual_pick``.
    """
    items: list[PlannedItem] = []
    used_variety_ids: set[uuid.UUID] = set()

    for day in context.target_days:
        needs_nonveg = day.date in context.nonveg_target_dates
        for template in context.slot_templates:
            for requirement in template.items:
                for _ in range(requirement.minimum):
                    desired_diet = "nonveg" if needs_nonveg else "veg"
                    dish = _pick(
                        context,
                        item_type=requirement.item_type,
                        desired_diet=desired_diet,
                        used_variety_ids=used_variety_ids,
                        quick=day.prep_bias == "quick",
                    )
                    if dish is None:
                        # Quota is explicitly softer than safety. Try the other diet (or either)
                        # before surfacing a manual pick, while still preserving every hard filter.
                        dish = _pick(
                            context,
                            item_type=requirement.item_type,
                            desired_diet=None,
                            used_variety_ids=used_variety_ids,
                            quick=day.prep_bias == "quick",
                        )
                    if dish is None:
                        items.append(
                            PlannedItem(
                                day=day.date,
                                slot=template.slot,
                                item_type=requirement.item_type,
                                dish_id=None,
                                status="needs_manual_pick",
                            )
                        )
                        continue
                    items.append(
                        PlannedItem(
                            day=day.date,
                            slot=template.slot,
                            item_type=requirement.item_type,
                            dish_id=dish.id,
                        )
                    )
                    if dish.track_variety:
                        used_variety_ids.add(dish.id)
                    if dish.veg_or_nonveg == "nonveg":
                        needs_nonveg = False

    return GeneratedPlan(
        week_start=context.week.week_start,
        items=tuple(items),
        source="fallback",
    )
