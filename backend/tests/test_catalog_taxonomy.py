"""MP-015/MP-017: unit tests for supabase/seed/catalog_taxonomy.py's inference rules — pure
functions, no database needed. Loaded via sys.path (not importlib-by-path like
test_load_master_catalogue.py) because catalog_taxonomy.py is imported normally by
ingest_catalog.py (`from catalog_taxonomy import ...`), so it needs to be importable by name too.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SEED_DIR = Path(__file__).resolve().parents[2] / "supabase" / "seed"
if str(_SEED_DIR) not in sys.path:
    sys.path.insert(0, str(_SEED_DIR))

from catalog_taxonomy import infer_dietary_flags, infer_meat_type  # noqa: E402


class TestInferMeatType:
    def test_veg_diet_has_no_meat_type(self) -> None:
        meat_type, low_confidence = infer_meat_type(
            diet="Vegetarian", subfamily="Poriyal", name="Cabbage Poriyal",
            main_ingredients="Cabbage",
        )
        assert meat_type is None
        assert low_confidence is False

    def test_egg_diet_has_no_meat_type(self) -> None:
        meat_type, _ = infer_meat_type(
            diet="Egg", subfamily="Egg", name="Muttai Poriyal", main_ingredients="Egg"
        )
        assert meat_type is None

    def test_chicken_from_main_ingredients(self) -> None:
        meat_type, low_confidence = infer_meat_type(
            diet="Non-Vegetarian", subfamily="Chicken gravy", name="Chicken Salna",
            main_ingredients="Chicken",
        )
        assert (meat_type, low_confidence) == ("chicken", False)

    def test_kozhi_keyword_catches_country_chicken(self) -> None:
        meat_type, _ = infer_meat_type(
            diet="Non-Vegetarian", subfamily="Biryani", name="Nattukozhi Biryani",
            main_ingredients="Nattukozhi",
        )
        assert meat_type == "chicken"

    def test_goat_keyword_maps_to_mutton(self) -> None:
        meat_type, _ = infer_meat_type(
            diet="Non-Vegetarian", subfamily="Mutton offal", name="Eeral Varuval",
            main_ingredients="Goat liver",
        )
        assert meat_type == "mutton"

    def test_main_ingredients_takes_priority_over_a_misleading_name(self) -> None:
        # "Vaankozhi" contains "kozhi" (chicken keyword) but Main Ingredient(s) already says
        # Turkey explicitly — the ingredient column must win, not a name substring.
        meat_type, low_confidence = infer_meat_type(
            diet="Non-Vegetarian", subfamily="Game/traditional",
            name="Vaankozhi Kuzhambu Tamil Style", main_ingredients="Turkey",
        )
        assert (meat_type, low_confidence) == ("other", False)

    def test_falls_back_to_subfamily_and_name_when_ingredients_dont_resolve_it(self) -> None:
        meat_type, _ = infer_meat_type(
            diet="Non-Vegetarian", subfamily="Chicken dry", name="Kongu Arisi Paruppu Kozhi Curry",
            main_ingredients="dal/rice spice profile",
        )
        assert meat_type == "chicken"

    def test_generic_meat_word_is_low_confidence_other(self) -> None:
        meat_type, low_confidence = infer_meat_type(
            diet="Non-Vegetarian", subfamily="Parotta", name="Kari Kothu Parotta",
            main_ingredients="Parotta + meat + salna",
        )
        assert (meat_type, low_confidence) == ("other", True)

    def test_truly_unresolvable_row_returns_none_not_a_guess(self) -> None:
        meat_type, low_confidence = infer_meat_type(
            diet="Non-Vegetarian", subfamily="Non-veg snack", name="Mystery Dish",
            main_ingredients=None,
        )
        assert (meat_type, low_confidence) == (None, False)


class TestInferDietaryFlags:
    def test_plain_veg_dish_gets_no_flags(self) -> None:
        flags = infer_dietary_flags(
            diet="Vegetarian", family="Poriyal", subfamily="Poriyal", name="Cabbage Poriyal",
            main_ingredients="Cabbage",
        )
        assert flags == []

    def test_dairy_keyword_tags_milk_dairy(self) -> None:
        flags = infer_dietary_flags(
            diet="Vegetarian", family="Sweet", subfamily="Sweet", name="Paal Payasam",
            main_ingredients="Milk + rice + jaggery",
        )
        assert "Milk-Dairy" in flags

    def test_coconut_is_not_tagged_as_nuts_or_dairy(self) -> None:
        flags = infer_dietary_flags(
            diet="Vegetarian", family="Kootu", subfamily="Kootu", name="Coconut Kootu",
            main_ingredients="Coconut + vegetables",
        )
        assert "Nuts" not in flags
        assert "Milk-Dairy" not in flags

    def test_peanut_is_folded_into_nuts(self) -> None:
        flags = infer_dietary_flags(
            diet="Vegetarian", family="Poriyal", subfamily="Poriyal", name="Peanut Chutney Poriyal",
            main_ingredients="Peanut + spices",
        )
        assert "Nuts" in flags

    def test_egg_diet_is_always_tagged_egg_even_without_the_word(self) -> None:
        flags = infer_dietary_flags(
            diet="Egg", family="Tiffin", subfamily="Rice-flour tiffin", name="Kalakki",
            main_ingredients="Egg",
        )
        assert "Egg" in flags

    def test_nonveg_dish_containing_egg_is_also_tagged_egg(self) -> None:
        # "Kari dosai" is Diet=Non-Vegetarian but its ingredients include egg alongside mutton —
        # the allergen flag must not be gated on the Diet column.
        flags = infer_dietary_flags(
            diet="Non-Vegetarian", family="Tiffin", subfamily="Dosai", name="Kari Dosai",
            main_ingredients="Dosa + minced mutton + egg",
        )
        assert "Egg" in flags

    def test_seafood_covers_both_fish_and_shellfish(self) -> None:
        fish_flags = infer_dietary_flags(
            diet="Non-Vegetarian", family="Kuzhambu", subfamily="Fish gravy", name="Meen Kuzhambu",
            main_ingredients="Fish",
        )
        crab_flags = infer_dietary_flags(
            diet="Non-Vegetarian", family="Kuzhambu", subfamily="Seafood", name="Nandu Kuzhambu",
            main_ingredients="Crab",
        )
        assert "Seafood" in fish_flags
        assert "Seafood" in crab_flags

    def test_sesame_keyword(self) -> None:
        flags = infer_dietary_flags(
            diet="Vegetarian", family="Snack", subfamily="Snack", name="Ellu Urundai",
            main_ingredients="Sesame + jaggery",
        )
        assert "Sesame" in flags

    def test_parotta_is_always_tagged_gluten_even_without_the_word_wheat(self) -> None:
        flags = infer_dietary_flags(
            diet="Non-Vegetarian", family="Tiffin", subfamily="Parotta", name="Kari Kothu Parotta",
            main_ingredients="Parotta + meat + salna",
        )
        assert "Gluten" in flags

    def test_result_is_always_a_sorted_list_never_none(self) -> None:
        flags = infer_dietary_flags(
            diet="Vegetarian", family="Rice dish", subfamily="Rice dish", name="Plain Rice",
            main_ingredients="Rice",
        )
        assert flags == []
        assert isinstance(flags, list)
