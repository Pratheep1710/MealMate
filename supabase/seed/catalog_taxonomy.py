"""MP-015/MP-017: taxonomy mapping rules for the master catalogue workbook ("Master Dishes" sheet).

Single source of truth shared by `ingest_catalog.py` (MP-018's real pipeline) and its tests —
`load_master_catalogue.py`'s one-time bulk load duplicated the family/diet maps inline; this pulls
that logic out so MP-018 doesn't retrofit the old script (Phase 5 brief §0 is explicit that MP-018
must not just be the seed script renamed).

Workbook column layout ("Master Dishes" sheet, 0-indexed, header row 1):
  0 Dish ID, 1 Meal Category, 2 Diet, 3 Dish Family, 4 Subfamily / Parent, 5 Specific Dish Variety,
  6 Tamil Name, 7 Main Ingredient(s), 8 Preparation Style, 9 Region / Style, 10 Common Pairing,
  11 Catalogue Note, 12 Source URL.

No column maps to `prep_minutes` — confirmed by inspecting the real workbook, not assumed. That's a
genuine data-collection gap (Phase 5 brief §0's third bullet), not something this module works
around: `infer_meat_type`/`infer_dietary_flags` below never touch prep_minutes, and
`ingest_catalog.py` leaves it untouched on every row it writes.
"""

from __future__ import annotations

FAMILY_TO_ITEM_TYPE: dict[str, str] = {
    "Snack": "snack",
    "Kuzhambu": "gravy",
    "Tiffin": "tiffin",
    "Varuval/Roast": "poriyal",
    "Kootu": "kootu",
    "Sweet": "sweet",
    "Poriyal": "poriyal",
    "Sambar": "gravy",
    "Rice dish": "rice",
    "Rasam": "gravy",
    "Traditional drink/porridge": "snack",
}

# Condiments/accompaniments — don't map to a standalone meal-slot item_type, so a row in one of
# these families is skipped rather than forced into an unrelated bucket.
CONDIMENT_ONLY_FAMILIES = frozenset(
    {"Chutney", "Accompaniment", "Thuvaiyal", "Pachadi", "Masiyal/Gothsu"}
)

DIET_TO_VEG_OR_NONVEG: dict[str, str] = {
    "Vegetarian": "veg",
    "Non-Vegetarian": "nonveg",
    "Egg": "nonveg",  # no separate "eggetarian" category in dishes.veg_or_nonveg's binary field
}

# item_types exempt from the 10-day variety rule (0001's own dishes.track_variety comment). This is
# the systematic, bulk-import rule — dev_placeholder_dishes.sql additionally hand-marks a few other
# everyday staples (murukku, payasam) false by editorial judgment; ingest_catalog.py deliberately
# never overwrites track_variety on an existing row (see its own docstring) so that judgment isn't
# clobbered by a re-run of this systematic rule.
NO_VARIETY_ITEM_TYPES = frozenset({"rice", "curd"})

MEAT_TYPE_VALUES = ("chicken", "mutton", "fish", "seafood", "other")

# Ordered: checked as substrings, most-specific first, against Main Ingredient(s) text alone in
# pass 1. "kozhi"/"meen" are Tamil for chicken/fish and are common enough in this workbook's Main
# Ingredient(s) column (e.g. "Country chicken", "Nattukozhi") to need covering directly rather than
# only via the English word.
_MEAT_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("chicken", "chicken"),
    ("kozhi", "chicken"),
    ("mutton", "mutton"),
    ("goat", "mutton"),
    ("fish", "fish"),
    ("meen", "fish"),
    ("sardine", "fish"),
    ("anchovy", "fish"),
    ("nethili", "fish"),
    ("snapper", "fish"),
    ("murrel", "fish"),
    ("ayirai", "fish"),
    ("prawn", "seafood"),
    ("shrimp", "seafood"),
    ("crab", "seafood"),
    ("nandu", "seafood"),
    ("squid", "seafood"),
    ("kanava", "seafood"),
    ("eral", "seafood"),
    ("oyster", "seafood"),
    ("lobster", "seafood"),
    ("quail", "other"),
    ("rabbit", "other"),
    ("turkey", "other"),
)
# Fallback pass only: generic "this is *some* meat" words too ambiguous to trust as a first-pass
# signal (e.g. "kari" is also a substring risk against unrelated text), used only once the specific
# keywords above have already failed to match anywhere.
_MEAT_TYPE_GENERIC_KEYWORDS = ("meat", "kari")


def infer_meat_type(*, diet: str, subfamily: str | None, name: str, main_ingredients: str | None) -> tuple[str | None, bool]:
    """Returns (meat_type, low_confidence). meat_type is None for veg/Egg-diet dishes (egg is a
    dietary_flag, not a meat preference — MP-017) or when nothing in the row's text identifies a
    protein at all (reported by the caller, not guessed). low_confidence marks a value chosen from
    the generic fallback pass ("kari"/"meat" alone) rather than a specific protein keyword, worth a
    human's second look even though it's not silently dropped.
    """
    if diet != "Non-Vegetarian":
        return None, False

    main_ingredients = main_ingredients or ""
    haystack_specific = main_ingredients.lower()
    for keyword, meat_type in _MEAT_TYPE_KEYWORDS:
        if keyword in haystack_specific:
            return meat_type, False

    # Main Ingredient(s) alone didn't resolve it (e.g. "dal/rice spice profile") — widen to
    # subfamily + the dish's own name, but only after the ingredient-only pass, so an unrelated
    # substring in the name (e.g. "Vaankozhi" containing "kozhi" for what Main Ingredient(s)
    # already correctly says is "Turkey") can't override a real ingredient-column answer.
    haystack_wide = f"{subfamily or ''} {name}".lower()
    for keyword, meat_type in _MEAT_TYPE_KEYWORDS:
        if keyword in haystack_wide:
            return meat_type, False

    for keyword in _MEAT_TYPE_GENERIC_KEYWORDS:
        if keyword in haystack_specific or keyword in haystack_wide:
            return "other", True

    return None, False


DIETARY_FLAG_VALUES = ("Nuts", "Milk-Dairy", "Gluten", "Egg", "Seafood", "Sesame")

# Checked as substrings against Main Ingredient(s) + Subfamily + name, combined, lowercased.
# Best-effort from the catalogue's own terse ingredient text — not a full recipe audit. See
# docs/MP-017-dietary-flag-taxonomy.md for the explicit human-review recommendation before this
# gates real user exclusions.
_DIETARY_FLAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Peanut/groundnut is botanically a legume, not a tree nut, but the decided vocabulary (Phase 5
    # brief §0) has no separate peanut flag — folded in here rather than left untagged, since a
    # peanut allergy is one of the most common in Tamil Nadu home cooking (chutneys, tempering) and
    # under-tagging a hard-exclusion allergen flag is the worse failure mode. "kadalai" is also used
    # for bengal gram in this cuisine, so this is a deliberately conservative (over-inclusive)
    # choice, not a precise one.
    "Nuts": ("cashew", "almond", "pista", "walnut", "peanut", "groundnut", "kadalai", "nuts"),
    "Milk-Dairy": ("milk", "curd", "yogurt", "paneer", "ghee", "butter", "cheese", "khoa", "malai"),
    # "coconut" is deliberately NOT a Milk-Dairy/Nuts keyword — coconut allergy is its own distinct,
    # much rarer category and most tree-nut-allergic people tolerate coconut; flagging it under
    # either bucket would over-exclude for the vast majority of this cuisine's dishes.
    "Gluten": ("wheat", "maida", "atta", "godhuma", "rava", "semolina"),
    "Egg": ("egg", "muttai"),
    "Seafood": (
        "fish", "meen", "sardine", "anchovy", "nethili", "snapper", "murrel", "ayirai",
        "prawn", "shrimp", "crab", "nandu", "squid", "kanava", "eral", "oyster", "lobster",
    ),
    "Sesame": ("sesame", "til", "ellu", "gingelly"),
}


def infer_dietary_flags(
    *, diet: str, family: str | None, subfamily: str | None, name: str, main_ingredients: str | None
) -> list[str]:
    """Evaluates all 6 controlled flags for every dish — always returns a list (possibly empty),
    never None, so every dish gets an explicit tag per flag per MP-017's AC rather than an
    untouched/unknown default.
    """
    haystack = " ".join(
        part for part in (main_ingredients, subfamily, name) if part
    ).lower()

    flags = [flag for flag, keywords in _DIETARY_FLAG_KEYWORDS.items() if any(k in haystack for k in keywords)]

    # Parotta is inherently wheat-flour dough — the catalogue's Main Ingredient(s) text for
    # non-veg parotta rows (e.g. "Parotta + meat + salna") never spells out "wheat", so the keyword
    # pass alone would miss it.
    if family == "Tiffin" and subfamily == "Parotta" and "Gluten" not in flags:
        flags.append("Gluten")

    # Belt-and-suspenders: an Egg-diet row is always egg-containing even if "egg"/"muttai" somehow
    # isn't in its ingredient text.
    if diet == "Egg" and "Egg" not in flags:
        flags.append("Egg")

    return sorted(flags)
