"""MP-029: typed models mirroring the Phase 1 Postgres schema (supabase/migrations/).

One class per table, field-for-field — these are what app/repositories/ functions return, so a
schema change and a model change should always land in the same commit.
"""

from app.models.availability import AvailableIngredient, GroceryListSnapshot
from app.models.dish import Dish, DishIngredient, Ingredient, IngredientAlias
from app.models.job import GenerationJob
from app.models.notification import NotificationLog
from app.models.plan import MealPlan, PlanItem
from app.models.profile import UserFavoriteDish, UserProfile

__all__ = [
    "AvailableIngredient",
    "Dish",
    "DishIngredient",
    "GenerationJob",
    "GroceryListSnapshot",
    "Ingredient",
    "IngredientAlias",
    "MealPlan",
    "NotificationLog",
    "PlanItem",
    "UserFavoriteDish",
    "UserProfile",
]
