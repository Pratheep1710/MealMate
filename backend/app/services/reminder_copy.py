"""MP-070: evening-before reminder copy. Pure composition, no I/O — kept separate from
app/services/push_dispatch.py's send call so the "idea, not plan" framing (docs/MP-001 "Core";
Phase 4 brief §1's copy requirement) is unit-testable without hitting the real Expo API.
"""

from __future__ import annotations

from app.repositories.plans import DaySlotSummary

_NIGHT_SLOT = "night"


def compose_reminder(day_plan: list[DaySlotSummary]) -> tuple[str, str] | None:
    """Returns (title, body) for tomorrow's push, or None if there's nothing worth nudging about
    yet (no plan computed for that date — the AC requires reading an "already-computed" plan, not
    inventing one).

    Deliberately "idea", never "plan": docs/MP-027-design-pass-scope.md's low-pressure framing —
    an edited/skipped slot is the product working, not something to warn about — carries into the
    notification's own copy, not just the in-app screens.
    """
    if not day_plan:
        return None

    night = next((slot for slot in day_plan if slot.slot == _NIGHT_SLOT), None)
    if night is None:
        return None

    if night.is_skipped:
        return ("Tomorrow night", "Cooking something of your own — nothing to prep.")

    if not night.dish_names:
        return None

    if len(night.dish_names) > 1:
        dish_text = " with ".join(night.dish_names)
    else:
        dish_text = night.dish_names[0]
    return ("Tomorrow's dinner idea", dish_text)
