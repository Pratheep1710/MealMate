"""Shared hard-eligibility policy for generated and fallback dish selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models import Dish, UserProfile
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


def is_egg_dish(dish: Dish) -> bool:
    """Egg dishes are stored as veg_or_nonveg='nonveg' + dietary_flags containing 'Egg' — there is
    no separate 'eggetarian' category on dishes (dishes.veg_or_nonveg is binary). The ingestion
    pipeline force-tags every egg-diet dish this way (supabase/seed/catalog_taxonomy.py's
    belt-and-suspenders note), so this is a reliable signal, not a heuristic.

    Routed through normalized_dietary_flags rather than reading dietary_flags directly, so missing
    or malformed metadata fails closed here too (returns False, same as "not an egg dish") instead
    of raising — is_eligible already rejects such a dish outright via its own `flags is not None`
    check, so this only needs to not crash on the way there.
    """
    flags = normalized_dietary_flags(dish)
    return dish.veg_or_nonveg == "nonveg" and flags is not None and "Egg" in flags


def diet_type_allows(dish: Dish, profile: UserProfile) -> bool:
    """Phase 8 (MP-024): hard diet-identity gate — Vegetarian/Eggetarian/meat-type-restricted
    exclusions never emerge only from target-date quota math, so a bug in that computation can't
    leak an inappropriate dish through. Day-based egg *permission* (which dates an egg dish is
    allowed on) is a separate, softer rule — see GenerationContext.egg_permitted_dates and its
    subset check in menu_validation.py; only the categorical 'never' case is handled here.

    Fail-closed on an unclassified real-meat dish (meat_type is null — the "genuinely ambiguous
    mixed meat" case 0016's own migration comment calls out) once the user has actually restricted
    meat_types: matches normalized_dietary_flags' existing fail-closed precedent for malformed
    metadata. Empty meat_types means unrestricted, matching empty dietary_restrictions.
    """
    if dish.veg_or_nonveg == "veg":
        return True
    if profile.diet_type == "vegetarian":
        return False
    if is_egg_dish(dish):
        return profile.egg_frequency != "never"
    if profile.diet_type != "nonvegetarian":
        return False
    return not profile.meat_types or dish.meat_type in profile.meat_types


def is_eligible(dish: Dish, context: GenerationContext) -> bool:
    """The single hard gate shared by response validation and fallback selection."""
    flags = normalized_dietary_flags(dish)
    return (
        dish.id in context.eligible_dish_ids
        and flags is not None
        and not (flags & frozenset(context.profile.dietary_restrictions))
        and diet_type_allows(dish, context.profile)
    )
