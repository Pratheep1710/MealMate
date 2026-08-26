"""MP-041–044 six-rule business validation for structured weekly menus."""

from __future__ import annotations

import collections
import datetime
from dataclasses import dataclass
from typing import Literal

from app.schemas.weekly_menu import WeeklyMenu
from app.services.generation_context import GenerationContext

ValidationCode = Literal[
    "candidate_membership",
    "in_week_repeat",
    "recent_repeat",
    "combo_template",
    "dietary_restriction",
    "nonveg_quota",
]


@dataclass(frozen=True)
class ValidationIssue:
    code: ValidationCode
    message: str


@dataclass(frozen=True)
class MenuValidation:
    issues: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def validate_menu(menu: WeeklyMenu, context: GenerationContext) -> MenuValidation:
    issues: list[ValidationIssue] = []
    dishes = context.dishes_by_id
    target_dates = set(context.target_dates)

    if menu.week_start != context.week.week_start:
        issues.append(
            ValidationIssue(
                "combo_template",
                f"week_start must be {context.week.week_start}, got {menu.week_start}",
            )
        )
    returned_dates = {item.day for item in menu.items}
    if returned_dates != target_dates:
        issues.append(
            ValidationIssue(
                "combo_template",
                "returned dates must exactly match target dates: "
                f"expected={sorted(target_dates)} actual={sorted(returned_dates)}",
            )
        )

    known_items = []
    for item in menu.items:
        dish = dishes.get(item.dish_id)
        if (
            dish is None
            or item.dish_id not in context.eligible_dish_ids
            or (dish is not None and dish.item_type != item.item_type)
        ):
            issues.append(
                ValidationIssue(
                    "candidate_membership",
                    f"{item.day}/{item.slot}/{item.item_type} uses an ineligible or "
                    "mismatched dish",
                )
            )
            continue
        known_items.append((item, dish))

    counts: collections.Counter[object] = collections.Counter(
        dish.id for _, dish in known_items if dish.track_variety
    )
    for dish_id, count in sorted(counts.items(), key=lambda pair: str(pair[0])):
        if count > 1:
            issues.append(
                ValidationIssue(
                    "in_week_repeat", f"track_variety dish {dish_id} appears {count} times"
                )
            )

    for item, dish in known_items:
        if dish.track_variety and dish.id in context.recent_dish_ids:
            issues.append(
                ValidationIssue(
                    "recent_repeat",
                    f"{item.day}: dish {dish.id} was used in the trailing 10-day window",
                )
            )
        conflicts = sorted(set(dish.dietary_flags) & set(context.profile.dietary_restrictions))
        if conflicts:
            issues.append(
                ValidationIssue(
                    "dietary_restriction",
                    f"{item.day}: dish {dish.id} conflicts with dietary restrictions: {conflicts}",
                )
            )

    by_day_slot: collections.Counter[tuple[datetime.date, str, str]] = collections.Counter(
        (item.day, item.slot, item.item_type) for item in menu.items
    )
    for day in sorted(target_dates):
        for template in context.slot_templates:
            expected_types = {requirement.item_type for requirement in template.items}
            actual_types = {
                item_type
                for item_day, slot, item_type in by_day_slot
                if item_day == day and slot == template.slot
            }
            if actual_types != expected_types:
                issues.append(
                    ValidationIssue(
                        "combo_template",
                        f"{day}/{template.slot} item types expected={sorted(expected_types)} "
                        f"actual={sorted(actual_types)}",
                    )
                )
            for requirement in template.items:
                count = by_day_slot[(day, template.slot, requirement.item_type)]
                if not requirement.minimum <= count <= requirement.maximum:
                    issues.append(
                        ValidationIssue(
                            "combo_template",
                            f"{day}/{template.slot}/{requirement.item_type} count {count} is "
                            "outside "
                            f"{requirement.minimum}..{requirement.maximum}",
                        )
                    )

    actual_nonveg_dates = {item.day for item, dish in known_items if dish.veg_or_nonveg == "nonveg"}
    if actual_nonveg_dates != set(context.nonveg_target_dates):
        issues.append(
            ValidationIssue(
                "nonveg_quota",
                "non-veg dates must match exactly: "
                f"expected={sorted(context.nonveg_target_dates)} "
                f"actual={sorted(actual_nonveg_dates)}",
            )
        )

    return MenuValidation(tuple(issues))
