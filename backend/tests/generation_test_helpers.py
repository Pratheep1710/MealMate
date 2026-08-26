from __future__ import annotations

import datetime
import uuid
from dataclasses import replace

from app.models import Dish, UserProfile
from app.schemas.weekly_menu import WeeklyMenu
from app.services.generation_context import CatalogGroup, GenerationContext
from app.services.slot_templates import GENERATION_ITEM_TYPES, templates_for_profile
from app.services.weekly_context import compute_weekly_context

WEEK_START = datetime.date(2026, 8, 24)


def make_dish(
    item_type: str,
    diet: str = "veg",
    *,
    track_variety: bool = False,
    dietary_flags: list[str] | None = None,
    name: str | None = None,
    prep_minutes: int | None = 20,
) -> Dish:
    return Dish(
        id=uuid.uuid4(),
        name=name or f"{diet} {item_type}",
        item_type=item_type,
        veg_or_nonveg=diet,
        region_style="Tamil Nadu",
        prep_minutes=prep_minutes,
        track_variety=track_variety,
        dietary_flags=dietary_flags or [],
    )


def make_context(
    *,
    planning_mode: str = "suggestion",
    dinner_style: str = "rice",
    restrictions: list[str] | None = None,
    day_count: int = 2,
) -> GenerationContext:
    profile = UserProfile(
        id=uuid.uuid4(),
        nonveg_days_per_week=1,
        nonveg_day_pattern=["mon"],
        dietary_restrictions=restrictions or [],
        dinner_style=dinner_style,
        planning_mode=planning_mode,
        grocery_day="monday",
        timezone="Asia/Kolkata",
    )
    week = compute_weekly_context(profile, WEEK_START)
    catalog = tuple(
        CatalogGroup(item_type, (make_dish(item_type), make_dish(item_type, "nonveg")))
        for item_type in GENERATION_ITEM_TYPES
    )
    candidate_ids = frozenset(dish.id for group in catalog for dish in group.dishes)
    return GenerationContext(
        profile=profile,
        week=week,
        target_days=week.days[:day_count],
        slot_templates=templates_for_profile(profile),
        catalog=catalog,
        recent_dish_ids=frozenset(),
        favorite_dish_ids=frozenset(),
        eligible_dish_ids=candidate_ids,
        available_ingredient_ids=frozenset(),
        last_used=(),
        nonveg_target_dates=frozenset({WEEK_START}),
    )


def menu_for_context(context: GenerationContext, *, include_nonveg: bool = True) -> WeeklyMenu:
    by_type_diet = {
        (dish.item_type, dish.veg_or_nonveg): dish
        for group in context.catalog
        for dish in group.dishes
    }
    items = []
    for day in context.target_days:
        nonveg_placed = not (include_nonveg and day.date in context.nonveg_target_dates)
        for template in context.slot_templates:
            for requirement in template.items:
                for _ in range(requirement.minimum):
                    diet = "veg"
                    if not nonveg_placed:
                        diet = "nonveg"
                        nonveg_placed = True
                    dish = by_type_diet[(requirement.item_type, diet)]
                    items.append(
                        {
                            "day": day.date,
                            "slot": template.slot,
                            "item_type": requirement.item_type,
                            "dish_id": dish.id,
                        }
                    )
    return WeeklyMenu(week_start=context.week.week_start, items=items)


def replace_dish(context: GenerationContext, old: Dish, new: Dish) -> GenerationContext:
    catalog = tuple(
        CatalogGroup(
            group.item_type,
            tuple(new if dish.id == old.id else dish for dish in group.dishes),
        )
        for group in context.catalog
    )
    eligible = (set(context.eligible_dish_ids) - {old.id}) | {new.id}
    return replace(context, catalog=catalog, eligible_dish_ids=frozenset(eligible))
