"""MP-038/039 static-first prompt construction for weekly generation."""

from __future__ import annotations

import json
from typing import Any, TypedDict

from app.services.generation_context import GenerationContext
from app.services.menu_validation import ValidationIssue


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
            "A date is non-veg when at least one selected dish is nonveg; "
            "match nonveg_target_dates exactly.",
            "Prefer lower prep_minutes on quick days and broader variety on flexible days.",
            "Only use IDs in eligible_dish_ids.",
        ],
        "slot_templates": {
            "morning": [{"item_type": "tiffin", "minimum": 1, "maximum": 1}],
            "afternoon": [
                {"item_type": "rice", "minimum": 1, "maximum": 1},
                {"item_type": "gravy", "minimum": 1, "maximum": 2},
                {"item_type": "poriyal", "minimum": 1, "maximum": 1},
            ],
            "night_alternatives": ["rice", "tiffin"],
            "snack_1": [{"item_type": "snack", "minimum": 1, "maximum": 1}],
            "snack_2": [{"item_type": "snack", "minimum": 1, "maximum": 1}],
            "snack_3": [{"item_type": "snack", "minimum": 1, "maximum": 1}],
        },
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
        },
        "selected_slot_templates": selected_templates,
        "nonveg_target_dates": sorted(date.isoformat() for date in context.nonveg_target_dates),
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
