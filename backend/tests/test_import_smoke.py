"""MP-029 AC: "package has clear modules for jobs, services, repositories, models" — verified by
actually importing every one of them and checking the expected callables/classes are there, not
just that the package directory exists.
"""

import importlib


def test_models_package_exports_one_class_per_table():
    models = importlib.import_module("app.models")
    for name in [
        "Dish",
        "Ingredient",
        "IngredientAlias",
        "DishIngredient",
        "UserProfile",
        "UserFavoriteDish",
        "MealPlan",
        "PlanItem",
        "GenerationJob",
        "NotificationLog",
        "AvailableIngredient",
        "GroceryListSnapshot",
    ]:
        assert hasattr(models, name), f"app.models is missing {name}"


def test_repositories_modules_import_and_expose_functions():
    for module_name, expected_functions in {
        "app.repositories.profiles": [
            "get_profile",
            "list_profiles",
            "upsert_profile",
            "list_favorite_dish_ids",
        ],
        "app.repositories.catalog": [
            "get_candidates",
            "get_reserves_eligible_dish_ids",
            "resolve_ingredient_alias",
        ],
        "app.repositories.history": [
            "get_recent_variety_dish_ids",
            "get_dish_last_used_dates",
            "get_nonveg_plan_dates",
        ],
        "app.repositories.availability": [
            "get_available_ingredient_ids",
            "set_available_ingredients",
        ],
        "app.repositories.plans": [
            "get_week_plan",
            "clear_plan_items_for_dates",
            "get_grocery_ingredient_rows",
            "write_grocery_snapshot",
        ],
        "app.repositories.jobs": [
            "claim_or_create_job",
            "try_start_processing",
            "try_restart_processing",
            "try_retry_failed",
            "update_job_status",
        ],
        "app.repositories.notifications": ["upsert_pending", "mark_status"],
    }.items():
        module = importlib.import_module(module_name)
        for fn in expected_functions:
            assert callable(getattr(module, fn, None)), (
                f"{module_name}.{fn} missing or not callable"
            )


def test_services_package_imports():
    module = importlib.import_module("app.services.notification_slo")
    assert callable(module.compute_daily_reminder_slo)


def test_phase3_services_import():
    for module_name, expected_functions in {
        "app.services.planning_trigger": ["compute_trigger"],
        "app.services.generation_claim": ["claim_job"],
        "app.services.variety_exclusion": ["get_variety_exclusion_set"],
        "app.services.weekly_context": ["compute_weekly_context"],
    }.items():
        module = importlib.import_module(module_name)
        for fn in expected_functions:
            assert callable(getattr(module, fn, None)), (
                f"{module_name}.{fn} missing or not callable"
            )


def test_phase6_generation_context_imports():
    for module_name, expected_function in {
        "app.services.generation_context": "build_generation_context",
        "app.services.generation_prompt": "build_generation_prompt",
        "app.services.menu_validation": "validate_menu",
        "app.services.rule_based_fallback": "build_fallback_plan",
        "app.services.plan_persistence": "persist_generated_plan",
        "app.services.generation_engine": "run_generation_engine",
    }.items():
        module = importlib.import_module(module_name)
        assert callable(getattr(module, expected_function))


def test_weekly_menu_schema_imports():
    module = importlib.import_module("app.schemas.weekly_menu")
    assert module.WeeklyMenu is not None
    assert module.WeeklyMenuItem is not None


def test_jobs_package_imports():
    module = importlib.import_module("app.jobs.entrypoints")
    assert callable(module.run_weekly_generation)
    assert callable(module.run_daily_reminder_dispatch)


def test_db_and_logging_and_main_import():
    assert callable(importlib.import_module("app.db").connect)
    assert callable(importlib.import_module("app.logging").get_logger)
    assert importlib.import_module("app.main").app is not None
