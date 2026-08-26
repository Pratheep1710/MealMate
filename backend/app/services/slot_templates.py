"""Phase 6 slot/combo templates for weekly generation.

The catalogue coverage gate has its own standalone copy because that admin script is deliberately
not part of the backend package. Runtime generation uses this module as its single source of truth
for both prompt construction and response validation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import UserProfile

SLOTS = ("morning", "afternoon", "night", "snack_1", "snack_2", "snack_3")

# Include both dinner branches so the static catalogue prefix is identical for every user. The
# user's selected dinner style only changes the dynamic slot template below.
GENERATION_ITEM_TYPES = ("tiffin", "rice", "gravy", "poriyal", "snack")


@dataclass(frozen=True)
class ItemRequirement:
    item_type: str
    minimum: int = 1
    maximum: int = 1


@dataclass(frozen=True)
class SlotTemplate:
    slot: str
    items: tuple[ItemRequirement, ...]


_MORNING = SlotTemplate("morning", (ItemRequirement("tiffin"),))
_AFTERNOON = SlotTemplate(
    "afternoon",
    (
        ItemRequirement("rice"),
        ItemRequirement("gravy", maximum=2),
        ItemRequirement("poriyal"),
    ),
)
_SNACKS = tuple(
    SlotTemplate(slot, (ItemRequirement("snack"),)) for slot in ("snack_1", "snack_2", "snack_3")
)


def _serialize(template: SlotTemplate) -> dict[str, object]:
    return {
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


def static_template_contract() -> dict[str, object]:
    """All valid template branches for the stable model prompt, from the runtime source."""
    return {
        "fixed_slots": [_serialize(_MORNING), _serialize(_AFTERNOON), *map(_serialize, _SNACKS)],
        "night_by_dinner_style": {
            dinner_style: _serialize(SlotTemplate("night", (ItemRequirement(dinner_style),)))
            for dinner_style in ("rice", "tiffin")
        },
        "instruction": (
            "Use exactly the night template named by the dynamic profile.dinner_style; "
            "the branches are alternatives, never interchangeable within one response."
        ),
    }


def templates_for_profile(profile: UserProfile) -> tuple[SlotTemplate, ...]:
    """Return the six runtime templates, resolving only the user's dinner-style branch.

    The afternoon counts come directly from technical spec section 5: one rice, one or two
    gravies, and one poriyal. The remaining mappings are the mappings documented and coverage-
    checked by MP-020.
    """
    if profile.dinner_style not in ("rice", "tiffin"):
        raise ValueError(f"unsupported dinner_style: {profile.dinner_style!r}")

    return (
        _MORNING,
        _AFTERNOON,
        SlotTemplate("night", (ItemRequirement(profile.dinner_style),)),
        *_SNACKS,
    )
