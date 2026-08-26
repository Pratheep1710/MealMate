from __future__ import annotations

from dataclasses import replace

from generation_test_helpers import make_context

from app.services.rule_based_fallback import build_fallback_plan


def test_fallback_fills_every_minimum_template_requirement() -> None:
    context = make_context()
    plan = build_fallback_plan(context)

    expected_per_day = sum(
        requirement.minimum for template in context.slot_templates for requirement in template.items
    )
    assert len(plan.items) == len(context.target_days) * expected_per_day
    assert all(item.status == "filled" for item in plan.items)
    assert plan.source == "fallback"


def test_fallback_never_selects_a_dietary_conflict() -> None:
    context = make_context(restrictions=["Nuts"])
    catalog = tuple(
        replace(
            group,
            dishes=tuple(
                dish.model_copy(update={"dietary_flags": ["Nuts"]})
                if dish.veg_or_nonveg == "nonveg"
                else dish
                for dish in group.dishes
            ),
        )
        for group in context.catalog
    )
    context = replace(context, catalog=catalog)

    plan = build_fallback_plan(context)
    dishes = context.dishes_by_id

    assert all(
        item.dish_id is None or not (set(dishes[item.dish_id].dietary_flags) & {"Nuts"})
        for item in plan.items
    )


def test_fallback_relaxes_recent_history_before_manual_pick() -> None:
    context = make_context()
    context = replace(context, recent_dish_ids=context.candidate_dish_ids)
    plan = build_fallback_plan(context)
    assert all(item.status == "filled" for item in plan.items)


def test_fallback_surfaces_manual_pick_when_safe_pool_is_empty() -> None:
    context = make_context()
    context = replace(context, eligible_dish_ids=frozenset())
    plan = build_fallback_plan(context)
    assert all(item.status == "needs_manual_pick" for item in plan.items)


def test_fallback_places_nonveg_on_the_target_date() -> None:
    context = make_context()
    plan = build_fallback_plan(context)
    dishes = context.dishes_by_id
    nonveg_dates = {
        item.day
        for item in plan.items
        if item.dish_id is not None and dishes[item.dish_id].veg_or_nonveg == "nonveg"
    }
    assert nonveg_dates == set(context.nonveg_target_dates)
