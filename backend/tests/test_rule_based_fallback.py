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


def test_fallback_relaxes_history_before_relaxing_nonveg_quota() -> None:
    context = make_context(day_count=1)
    tiffins = next(group.dishes for group in context.catalog if group.item_type == "tiffin")
    recent_nonveg = next(dish for dish in tiffins if dish.veg_or_nonveg == "nonveg")
    fresh_veg = next(dish for dish in tiffins if dish.veg_or_nonveg == "veg")
    context = replace(context, recent_dish_ids=frozenset({recent_nonveg.id}))

    plan = build_fallback_plan(context)
    morning = next(item for item in plan.items if item.slot == "morning")

    assert morning.dish_id == recent_nonveg.id
    assert morning.dish_id != fresh_veg.id


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
    assert nonveg_dates == set(context.meat_target_dates)


def test_fallback_never_selects_meat_for_a_vegetarian_profile() -> None:
    # Vegetarian profiles are DB-constrained to nonveg_days_per_week=0 (0021_onboarding_diet_
    # taxonomy.sql), but this is the hard gate itself (diet_type_allows), not an emergent property
    # of the quota — a bug in target-date computation must not be able to leak a Vegetarian a meat
    # or egg dish.
    context = make_context(diet_type="vegetarian", egg_frequency=None)
    plan = build_fallback_plan(context)
    dishes = context.dishes_by_id
    assert all(
        item.dish_id is None or dishes[item.dish_id].veg_or_nonveg == "veg" for item in plan.items
    )


def test_fallback_never_selects_real_meat_for_an_eggetarian_profile() -> None:
    context = make_context(diet_type="eggetarian", egg_frequency="any")
    catalog = tuple(
        replace(
            group,
            dishes=tuple(
                dish.model_copy(update={"dietary_flags": ["Egg"], "meat_type": None})
                if dish.veg_or_nonveg == "nonveg"
                else dish
                for dish in group.dishes
            ),
        )
        for group in context.catalog
    )
    context = replace(context, catalog=catalog, eligible_dish_ids=context.candidate_dish_ids)
    plan = build_fallback_plan(context)
    dishes = context.dishes_by_id
    assert all(
        item.dish_id is None
        or dishes[item.dish_id].veg_or_nonveg == "veg"
        or "Egg" in dishes[item.dish_id].dietary_flags
        for item in plan.items
    )


def test_fallback_respects_a_restricted_meat_types_preference() -> None:
    context = make_context(diet_type="nonvegetarian", meat_types=["chicken"], egg_frequency="never")
    catalog = tuple(
        replace(
            group,
            dishes=tuple(
                dish.model_copy(update={"meat_type": "mutton"})
                if dish.veg_or_nonveg == "nonveg"
                else dish
                for dish in group.dishes
            ),
        )
        for group in context.catalog
    )
    context = replace(context, catalog=catalog, eligible_dish_ids=context.candidate_dish_ids)
    plan = build_fallback_plan(context)
    dishes = context.dishes_by_id
    # Every nonveg dish in this catalog is meat_type='mutton', which isn't in meat_types=['chicken']
    # — none should ever be selected, forcing veg (or needs_manual_pick, never mutton).
    assert all(
        item.dish_id is None or dishes[item.dish_id].veg_or_nonveg == "veg" for item in plan.items
    )
