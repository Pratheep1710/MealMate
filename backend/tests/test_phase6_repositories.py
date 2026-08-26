from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from app.repositories import catalog as catalog_repo
from app.repositories import history as history_repo
from app.repositories import jobs as jobs_repo
from app.repositories import plans as plans_repo
from app.repositories import profiles as profiles_repo
from app.services.generation_models import GeneratedPlan, PlannedItem
from app.services.plan_persistence import persist_generated_plan

_WEEK_START = datetime.date(2026, 8, 24)


def _dish(conn, name: str, *, diet: str = "veg") -> uuid.UUID:
    return conn.execute(
        """
        insert into dishes (name, item_type, veg_or_nonveg, dietary_flags)
        values (%s, 'tiffin', %s, '{}') returning id
        """,
        (name, diet),
    ).fetchone()["id"]


def _ingredient(conn, name: str, *, staple: bool = False) -> uuid.UUID:
    return conn.execute(
        "insert into ingredients (canonical_name, is_staple) values (%s, %s) returning id",
        (name, staple),
    ).fetchone()["id"]


def test_reserves_eligibility_requires_every_nonstaple_ingredient(conn) -> None:
    onion = _ingredient(conn, "Onion")
    rice = _ingredient(conn, "Rice", staple=True)
    eligible = _dish(conn, "Eligible")
    missing = _dish(conn, "Missing tomato")
    tomato = _ingredient(conn, "Tomato")
    conn.execute(
        "insert into dish_ingredients (dish_id, ingredient_id) values (%s, %s), (%s, %s), (%s, %s)",
        (eligible, onion, eligible, rice, missing, tomato),
    )

    result = catalog_repo.get_reserves_eligible_dish_ids(conn, [eligible, missing], [onion])

    assert result == [eligible]


def test_history_queries_last_use_and_prior_nonveg_dates(conn, make_user) -> None:
    user_id = make_user()
    dish_id = _dish(conn, "Chicken", diet="nonveg")
    plan = plans_repo.create_plan_day(conn, user_id, _WEEK_START, "morning")
    plans_repo.add_plan_item(conn, plan.id, "tiffin", dish_id)

    assert history_repo.get_dish_last_used_dates(
        conn, user_id, _WEEK_START + datetime.timedelta(days=2)
    ) == {dish_id: _WEEK_START}
    assert history_repo.get_nonveg_plan_dates(
        conn,
        user_id,
        _WEEK_START,
        _WEEK_START + datetime.timedelta(days=2),
    ) == {_WEEK_START}


def test_partial_clear_preserves_earlier_plan_items(conn, make_user) -> None:
    user_id = make_user()
    dish_id = _dish(conn, "Idli")
    first = plans_repo.create_plan_day(conn, user_id, _WEEK_START, "morning")
    second_date = _WEEK_START + datetime.timedelta(days=1)
    second = plans_repo.create_plan_day(conn, user_id, second_date, "morning")
    plans_repo.add_plan_item(conn, first.id, "tiffin", dish_id)
    plans_repo.add_plan_item(conn, second.id, "tiffin", dish_id)

    plans_repo.clear_plan_items_for_dates(conn, user_id, [second_date])

    assert len(plans_repo.get_plan_items(conn, first.id)) == 1
    assert plans_repo.get_plan_items(conn, second.id) == []


def test_grocery_rows_preserve_each_plan_occurrence_and_quantity(conn, make_user) -> None:
    user_id = make_user()
    dish_id = _dish(conn, "Onion dish")
    onion = _ingredient(conn, "Onion")
    conn.execute(
        """
        insert into dish_ingredients (dish_id, ingredient_id, quantity, unit)
        values (%s, %s, %s, 'kg')
        """,
        (dish_id, onion, Decimal("0.5")),
    )
    for offset in range(2):
        plan = plans_repo.create_plan_day(
            conn, user_id, _WEEK_START + datetime.timedelta(days=offset), "morning"
        )
        plans_repo.add_plan_item(conn, plan.id, "tiffin", dish_id)

    rows = plans_repo.get_grocery_ingredient_rows(
        conn,
        user_id,
        [_WEEK_START, _WEEK_START + datetime.timedelta(days=1)],
    )

    assert [row.quantity for row in rows] == [Decimal("0.5"), Decimal("0.5")]


def test_explicit_regenerate_can_restart_a_completed_job(conn, make_user) -> None:
    user_id = make_user()
    job = jobs_repo.claim_or_create_job(conn, user_id, _WEEK_START)
    started = jobs_repo.try_start_processing(conn, job.id)
    assert started is not None
    jobs_repo.update_job_status(conn, job.id, "done")

    restarted = jobs_repo.try_restart_processing(conn, job.id)

    assert restarted is not None
    assert restarted.status == "processing"


def test_scheduled_retry_reopens_failed_but_not_completed_jobs(conn, make_user) -> None:
    user_id = make_user()
    failed = jobs_repo.claim_or_create_job(conn, user_id, _WEEK_START)
    jobs_repo.try_start_processing(conn, failed.id)
    jobs_repo.update_job_status(conn, failed.id, "failed")

    retried = jobs_repo.try_retry_failed(conn, failed.id)

    assert retried is not None
    assert retried.status == "processing"
    jobs_repo.update_job_status(conn, failed.id, "done")
    assert jobs_repo.try_retry_failed(conn, failed.id) is None


def test_profile_sweep_lists_each_profile(conn, make_user) -> None:
    users = {make_user(), make_user()}
    assert users <= {profile.id for profile in profiles_repo.list_profiles(conn)}


def test_grocery_snapshot_rewrite_preserves_the_original_frozen_timestamp(conn, make_user) -> None:
    user_id = make_user()
    plans_repo.write_grocery_snapshot(conn, user_id, _WEEK_START, [{"name": "Onion"}])
    frozen_at = datetime.datetime(2026, 1, 2, 3, 4, tzinfo=datetime.UTC)
    conn.execute(
        "update grocery_list_snapshot set created_at = %s where user_id = %s and week_start = %s",
        (frozen_at, user_id, _WEEK_START),
    )

    rewritten = plans_repo.write_grocery_snapshot(conn, user_id, _WEEK_START, [{"name": "Tomato"}])

    assert rewritten.created_at == frozen_at
    assert rewritten.ingredients == [{"name": "Tomato"}]


def test_persist_generated_plan_replaces_items_builds_snapshot_and_outbox(conn, make_user) -> None:
    user_id = make_user()
    profile = profiles_repo.get_profile(conn, user_id)
    assert profile is not None
    earlier_dish_id = _dish(conn, "Earlier tomato tiffin")
    tomato = _ingredient(conn, "Tomato")
    conn.execute(
        "insert into dish_ingredients (dish_id, ingredient_id) values (%s, %s)",
        (earlier_dish_id, tomato),
    )
    earlier = plans_repo.create_plan_day(conn, user_id, _WEEK_START, "morning")
    plans_repo.add_plan_item(conn, earlier.id, "tiffin", earlier_dish_id)

    dish_id = _dish(conn, "Onion tiffin")
    onion = _ingredient(conn, "Onion")
    conn.execute(
        """
        insert into dish_ingredients (dish_id, ingredient_id, quantity, unit)
        values (%s, %s, 2, 'piece')
        """,
        (dish_id, onion),
    )
    regenerated_date = _WEEK_START + datetime.timedelta(days=1)
    plan = GeneratedPlan(
        week_start=_WEEK_START,
        items=(PlannedItem(regenerated_date, "morning", "tiffin", dish_id),),
        source="fallback",
    )

    result = persist_generated_plan(conn, user_id, profile, plan, frozenset())

    meal_plan = plans_repo.get_week_plan(conn, user_id, _WEEK_START)
    assert len(meal_plan) == 2
    regenerated = next(plan for plan in meal_plan if plan.plan_date == regenerated_date)
    assert plans_repo.get_plan_items(conn, regenerated.id)[0].dish_id == dish_id
    assert {item["name"] for item in result.snapshot.ingredients} == {"Onion"}
    assert result.snapshot.ingredients[0]["quantity"] == "2"
    assert result.notification.notification_type == "week_ready"
