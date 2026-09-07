"""MP-038/039 static-first prompt construction for weekly generation."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from app.services.generation_context import GenerationContext
from app.services.menu_validation import ValidationIssue
from app.services.slot_templates import static_template_contract


class PromptMessage(TypedDict):
    role: str
    content: str


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_generation_prompt(
    context: GenerationContext,
    *,
    retry_issues: tuple[ValidationIssue, ...] = (),
) -> list[PromptMessage]:
    """Stable catalogue/instructions first; compact per-user data and retry feedback last."""
    selected_templates = [
        {
            "slot": template.slot,
            "items": [
                {
                    "item_type": item.item_type,
                    "minimum": item.minimum,
                    "maximum": item.maximum,
                }
                for item in template.items
            ],
        }
        for template in context.slot_templates
    ]
    catalog = [
        {
            "id": str(dish.id),
            "name": dish.name,
            "item_type": dish.item_type,
            "veg_or_nonveg": dish.veg_or_nonveg,
            "prep_minutes": dish.prep_minutes,
            "track_variety": dish.track_variety,
            "dietary_flags": dish.dietary_flags,
            "meat_type": dish.meat_type,
        }
        for group in context.catalog
        for dish in group.dishes
    ]
    static = {
        "task": "Compose a Tamil Nadu weekly meal menu using only the supplied dish IDs.",
        "rules": [
            "Return every target date and all six slots.",
            "Match each slot template's item counts.",
            "Never repeat a track_variety dish within this output.",
            "Never use a recent_dish_id.",
            "Never use a dish whose dietary_flags intersect dietary_restrictions.",
            "A date is a meat date when at least one selected dish is nonveg and does not have "
            "'Egg' in dietary_flags; match meat_target_dates exactly.",
            "A dish with 'Egg' in dietary_flags may only be used on a date in egg_permitted_dates.",
            "If profile.diet_type is 'vegetarian', never select a nonveg dish (meat or egg).",
            "If profile.diet_type is 'eggetarian', never select a nonveg dish unless it has "
            "'Egg' in dietary_flags (no real meat, ever).",
            "If profile.diet_type is 'nonvegetarian' and profile.meat_types is non-empty, a "
            "non-egg nonveg dish's meat_type must be one of profile.meat_types.",
            "Prefer lower prep_minutes on quick days and broader variety on flexible days.",
            "Only use IDs in eligible_dish_ids.",
        ],
        "slot_templates": static_template_contract(),
        "catalog": catalog,
    }
    dynamic = {
        "week_start": context.week.week_start.isoformat(),
        "target_days": [
            {"date": day.date.isoformat(), "prep_bias": day.prep_bias}
            for day in context.target_days
        ],
        "profile": {
            "dietary_restrictions": context.profile.dietary_restrictions,
            "dinner_style": context.profile.dinner_style,
            "planning_mode": context.profile.planning_mode,
            "diet_type": context.profile.diet_type,
            "meat_types": context.profile.meat_types,
            "egg_frequency": context.profile.egg_frequency,
        },
        "selected_slot_templates": selected_templates,
        "meat_target_dates": sorted(date.isoformat() for date in context.meat_target_dates),
        "egg_permitted_dates": sorted(date.isoformat() for date in context.egg_permitted_dates),
        "recent_dish_ids": sorted(str(dish_id) for dish_id in context.recent_dish_ids),
        "eligible_dish_ids": sorted(str(dish_id) for dish_id in context.eligible_dish_ids),
        "available_ingredient_ids": sorted(
            str(ingredient_id) for ingredient_id in context.available_ingredient_ids
        ),
    }
    messages: list[PromptMessage] = [
        {"role": "developer", "content": _json(static)},
        {"role": "user", "content": _json(dynamic)},
    ]
    if retry_issues:
        feedback = {
            "retry": True,
            "instruction": "Correct every listed validation issue; return the complete menu again.",
            "issues": [{"code": issue.code, "message": issue.message} for issue in retry_issues],
        }
        messages.append({"role": "user", "content": _json(feedback)})
    return messages
