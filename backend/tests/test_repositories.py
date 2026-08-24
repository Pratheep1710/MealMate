"""MP-031: repository integration tests, run against the real Phase 1 schema (see conftest.py).

Skips automatically when no local Postgres is reachable — this is the "not skip, fail" gate for
POSTGRES_TEST_HOST etc. being unset, mirroring how test_supabase_auth.py skips without live creds.
"""

from __future__ import annotations

import datetime
import uuid

from app.models import UserProfile
from app.repositories import availability as availability_repo
from app.repositories import catalog as catalog_repo
from app.repositories import history as history_repo
from app.repositories import jobs as jobs_repo
from app.repositories import notifications as notifications_repo
from app.repositories import plans as plans_repo
from app.repositories import profiles as profiles_repo
from app.services import variety_exclusion as variety_exclusion_service


def _insert_dish(
    conn,
    *,
    name: str,
    item_type: str = "poriyal",
    veg_or_nonveg: str = "veg",
    track_variety: bool = True,
    dietary_flags: list[str] | None = None,
) -> uuid.UUID:
    row = conn.execute(
        """
        insert into dishes (name, item_type, veg_or_nonveg, track_variety, dietary_flags)
        values (%s, %s, %s, %s, %s)
        returning id
        """,
        (name, item_type, veg_or_nonveg, track_variety, dietary_flags or []),
    ).fetchone()
    return row["id"]


def _insert_ingredient(conn, *, canonical_name: str, is_staple: bool = False) -> uuid.UUID:
    row = conn.execute(
        "insert into ingredients (canonical_name, is_staple) values (%s, %s) returning id",
        (canonical_name, is_staple),
    ).fetchone()
    return row["id"]


class TestProfilesRepository:
    def test_upsert_and_get_round_trips(self, conn, make_user):
        user_id = make_user()
        profile = UserProfile(
            id=user_id,
            nonveg_days_per_week=2,
            nonveg_day_pattern=["wed", "sat"],
            dietary_restrictions=["dairy"],
            dinner_style="tiffin",
            planning_mode="reserves",
            grocery_day="sunday",
            timezone="Asia/Kolkata",
        )
        profiles_repo.upsert_profile(conn, profile)

        fetched = profiles_repo.get_profile(conn, user_id)
        assert fetched is not None
        assert fetched.dinner_style == "tiffin"
        assert fetched.dietary_restrictions == ["dairy"]

    def test_get_profile_returns_none_for_unknown_user(self, conn):
        assert profiles_repo.get_profile(conn, uuid.uuid4()) is None

    def test_favorites_are_scoped_per_user(self, conn, make_user):
        user_a = make_user()
        user_b = make_user()
        dish_id = _insert_dish(conn, name="Favorite Dish")

        profiles_repo.add_favorite(conn, user_a, dish_id)

        assert profiles_repo.list_favorite_dish_ids(conn, user_a) == [dish_id]
        assert profiles_repo.list_favorite_dish_ids(conn, user_b) == []

        profiles_repo.remove_favorite(conn, user_a, dish_id)
        assert profiles_repo.list_favorite_dish_ids(conn, user_a) == []

    def test_planning_mode_is_insert_only_and_ignores_later_changes(self, conn, make_user):
        """Regression: upsert_profile used to include `planning_mode` in its ON CONFLICT UPDATE
        SET clause, so any later upsert silently changed it — bypassing functional spec §2's
        onboarding-only invariant. Migration 0009 enforces this for the `authenticated` role's own
        column grant, but this backend connection uses a more privileged role that grant doesn't
        restrict, so the repository itself has to hold the line.
        """
        user_id = make_user()
        onboarding_profile = UserProfile(
            id=user_id,
            nonveg_days_per_week=None,
            nonveg_day_pattern=None,
            dietary_restrictions=[],
            dinner_style="rice",
            planning_mode="suggestion",
            grocery_day="monday",
            timezone="Asia/Kolkata",
        )
        profiles_repo.upsert_profile(conn, onboarding_profile)

        later_edit = onboarding_profile.model_copy(
            update={"planning_mode": "reserves", "dinner_style": "tiffin"}
        )
        updated = profiles_repo.upsert_profile(conn, later_edit)

        assert updated.planning_mode == "suggestion"
        assert updated.dinner_style == "tiffin"


class TestCatalogRepository:
    def test_get_candidates_filters_by_item_type_and_veg(self, conn):
        _insert_dish(conn, name="Veg Poriyal", item_type="poriyal", veg_or_nonveg="veg")
        _insert_dish(conn, name="Nonveg Poriyal", item_type="poriyal", veg_or_nonveg="nonveg")
        _insert_dish(conn, name="Veg Kootu", item_type="kootu", veg_or_nonveg="veg")

        candidates = catalog_repo.get_candidates(conn, item_type="poriyal", veg_or_nonveg="veg")

        assert [c.name for c in candidates] == ["Veg Poriyal"]

    def test_get_candidates_hard_excludes_dietary_flags(self, conn):
        _insert_dish(conn, name="Has Dairy", item_type="sweet", dietary_flags=["dairy"])
        _insert_dish(conn, name="No Dairy", item_type="sweet", dietary_flags=[])

        candidates = catalog_repo.get_candidates(
            conn, item_type="sweet", exclude_dietary_flags=["dairy"]
        )

        assert [c.name for c in candidates] == ["No Dairy"]

    def test_get_candidates_excludes_given_dish_ids(self, conn):
        keep_id = _insert_dish(conn, name="Keep", item_type="rice")
        exclude_id = _insert_dish(conn, name="Exclude", item_type="rice")

        candidates = catalog_repo.get_candidates(
            conn, item_type="rice", exclude_dish_ids=[exclude_id]
        )

        assert [c.id for c in candidates] == [keep_id]

    def test_ingredient_alias_resolves_to_canonical_ingredient(self, conn):
        ingredient_id = _insert_ingredient(conn, canonical_name="Tomato")
        conn.execute(
            "insert into ingredient_aliases (alias_text, ingredient_id) values (%s, %s)",
            ("thakkali", ingredient_id),
        )

        resolved = catalog_repo.resolve_ingredient_alias(conn, "thakkali")

        assert resolved is not None
        assert resolved.id == ingredient_id
        assert resolved.canonical_name == "Tomato"

    def test_unknown_alias_resolves_to_none(self, conn):
        assert catalog_repo.resolve_ingredient_alias(conn, "not-a-real-alias") is None


class TestHistoryRepository:
    def test_recent_variety_dishes_excludes_staples_and_old_history(self, conn, make_user):
        user_id = make_user()
        profiles_repo.upsert_profile(
            conn,
            UserProfile(
                id=user_id,
                nonveg_days_per_week=None,
                nonveg_day_pattern=None,
                dietary_restrictions=[],
                dinner_style="rice",
                planning_mode="suggestion",
                grocery_day="monday",
                timezone="Asia/Kolkata",
            ),
        )
        variety_dish = _insert_dish(conn, name="Variety Dish", track_variety=True)
        staple_dish = _insert_dish(conn, name="Staple Rice", item_type="rice", track_variety=False)
        old_dish = _insert_dish(conn, name="Old Dish", track_variety=True)

        recent_plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 20), "night")
        plans_repo.add_plan_item(conn, recent_plan.id, "poriyal", variety_dish)
        plans_repo.add_plan_item(conn, recent_plan.id, "rice", staple_dish)

        old_plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 1), "night")
        plans_repo.add_plan_item(conn, old_plan.id, "poriyal", old_dish)

        recent_ids = history_repo.get_recent_variety_dish_ids(
            conn, user_id, datetime.date(2026, 8, 15), datetime.date(2026, 8, 25)
        )

        assert recent_ids == [variety_dish]

    def test_recent_variety_dishes_excludes_skipped_days(self, conn, make_user):
        """Regression: a dish attached to a skipped/eating-out day (meal_plans.is_skipped)
        previously still counted toward the 10-day variety history, even though functional spec
        §6 requires skipped slots to drop out of variety/history tracking entirely.
        """
        user_id = make_user()
        dish_id = _insert_dish(conn, name="Skipped Day Dish", track_variety=True)

        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 20), "night")
        plans_repo.add_plan_item(conn, plan.id, "poriyal", dish_id)
        plans_repo.set_plan_skipped(conn, plan.id, True)

        recent_ids = history_repo.get_recent_variety_dish_ids(
            conn, user_id, datetime.date(2026, 8, 15), datetime.date(2026, 8, 25)
        )

        assert recent_ids == []

    def test_before_bound_is_exclusive(self, conn, make_user):
        """Regression: get_recent_variety_dish_ids had no upper bound at all, so a dish served on
        or after `before` (today's own assignment, or a future generated week's) would count as
        its own history and wrongly exclude itself.
        """
        user_id = make_user()
        dish_id = _insert_dish(conn, name="Served On The Before Date", track_variety=True)
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 25), "night")
        plans_repo.add_plan_item(conn, plan.id, "poriyal", dish_id)

        recent_ids = history_repo.get_recent_variety_dish_ids(
            conn, user_id, datetime.date(2026, 8, 15), datetime.date(2026, 8, 25)
        )

        assert recent_ids == []


class TestVarietyExclusionService:
    """MP-035: 10-day exclusion set, boundary dates and favorite exemption."""

    def test_exactly_ten_days_ago_is_excluded(self, conn, make_user):
        user_id = make_user()
        as_of = datetime.date(2026, 8, 24)
        dish_id = _insert_dish(conn, name="Ten Days Ago")
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 14), "night")
        plans_repo.add_plan_item(conn, plan.id, "poriyal", dish_id)

        exclusion = variety_exclusion_service.get_variety_exclusion_set(conn, user_id, as_of)

        assert dish_id in exclusion

    def test_eleven_days_ago_is_not_excluded(self, conn, make_user):
        user_id = make_user()
        as_of = datetime.date(2026, 8, 24)
        dish_id = _insert_dish(conn, name="Eleven Days Ago")
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 13), "night")
        plans_repo.add_plan_item(conn, plan.id, "poriyal", dish_id)

        exclusion = variety_exclusion_service.get_variety_exclusion_set(conn, user_id, as_of)

        assert dish_id not in exclusion

    def test_favorites_are_exempt_even_when_served_recently(self, conn, make_user):
        user_id = make_user()
        as_of = datetime.date(2026, 8, 24)
        favorite_id = _insert_dish(conn, name="Favorite Served Recently")
        profiles_repo.add_favorite(conn, user_id, favorite_id)
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 20), "night")
        plans_repo.add_plan_item(conn, plan.id, "poriyal", favorite_id)

        exclusion = variety_exclusion_service.get_variety_exclusion_set(conn, user_id, as_of)

        assert favorite_id not in exclusion

    def test_non_favorite_recent_dish_is_still_excluded(self, conn, make_user):
        user_id = make_user()
        as_of = datetime.date(2026, 8, 24)
        dish_id = _insert_dish(conn, name="Not A Favorite")
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 20), "night")
        plans_repo.add_plan_item(conn, plan.id, "poriyal", dish_id)

        exclusion = variety_exclusion_service.get_variety_exclusion_set(conn, user_id, as_of)

        assert dish_id in exclusion

    def test_a_dish_served_on_as_of_itself_is_not_excluded(self, conn, make_user):
        """Regression: as_of's own generated day (today, or the day being generated) must never
        exclude itself from its own candidate pool.
        """
        user_id = make_user()
        as_of = datetime.date(2026, 8, 24)
        dish_id = _insert_dish(conn, name="Served Today")
        plan = plans_repo.create_plan_day(conn, user_id, as_of, "morning")
        plans_repo.add_plan_item(conn, plan.id, "poriyal", dish_id)

        exclusion = variety_exclusion_service.get_variety_exclusion_set(conn, user_id, as_of)

        assert dish_id not in exclusion

    def test_a_dish_served_in_a_future_generated_week_is_not_excluded(self, conn, make_user):
        """Regression: a dish already assigned in a future week (e.g. from an earlier
        regenerate-remaining-week call) must not exclude itself when computing an earlier day's
        candidate pool.
        """
        user_id = make_user()
        as_of = datetime.date(2026, 8, 24)
        dish_id = _insert_dish(conn, name="Served Next Week")
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 30), "night")
        plans_repo.add_plan_item(conn, plan.id, "poriyal", dish_id)

        exclusion = variety_exclusion_service.get_variety_exclusion_set(conn, user_id, as_of)

        assert dish_id not in exclusion


class TestAvailabilityRepository:
    def test_set_available_ingredients_replaces_the_whole_set(self, conn, make_user):
        user_id = make_user()
        week_start = datetime.date(2026, 8, 24)
        ing_a = _insert_ingredient(conn, canonical_name="Onion")
        ing_b = _insert_ingredient(conn, canonical_name="Carrot")

        availability_repo.set_available_ingredients(conn, user_id, week_start, [ing_a])
        assert set(availability_repo.get_available_ingredient_ids(conn, user_id, week_start)) == {
            ing_a
        }

        availability_repo.set_available_ingredients(conn, user_id, week_start, [ing_b])
        assert set(availability_repo.get_available_ingredient_ids(conn, user_id, week_start)) == {
            ing_b
        }

    def test_set_available_ingredients_to_empty_clears_it(self, conn, make_user):
        user_id = make_user()
        week_start = datetime.date(2026, 8, 24)
        ing_a = _insert_ingredient(conn, canonical_name="Onion")

        availability_repo.set_available_ingredients(conn, user_id, week_start, [ing_a])
        availability_repo.set_available_ingredients(conn, user_id, week_start, [])

        assert availability_repo.get_available_ingredient_ids(conn, user_id, week_start) == []


class TestPlansRepository:
    def test_create_plan_day_is_idempotent_per_unique_constraint(self, conn, make_user):
        user_id = make_user()
        plan_date = datetime.date(2026, 8, 24)

        first = plans_repo.create_plan_day(conn, user_id, plan_date, "morning")
        second = plans_repo.create_plan_day(conn, user_id, plan_date, "morning")

        assert first.id == second.id

    def test_add_and_remove_plan_item(self, conn, make_user):
        user_id = make_user()
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 24), "night")
        dish_id = _insert_dish(conn, name="Dinner Dish")

        item = plans_repo.add_plan_item(conn, plan.id, "poriyal", dish_id, make_extra=True)
        assert item.make_extra is True
        assert [i.id for i in plans_repo.get_plan_items(conn, plan.id)] == [item.id]

        plans_repo.remove_plan_item(conn, item.id)
        assert plans_repo.get_plan_items(conn, plan.id) == []

    def test_needs_manual_pick_item_round_trips_with_null_dish_id(self, conn, make_user):
        user_id = make_user()
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 24), "night")

        conn.execute(
            """
            insert into plan_items (plan_id, item_type, dish_id, status)
            values (%s, %s, null, 'needs_manual_pick')
            """,
            (plan.id, "poriyal"),
        )

        items = plans_repo.get_plan_items(conn, plan.id)

        assert len(items) == 1
        assert items[0].dish_id is None
        assert items[0].status == "needs_manual_pick"

    def test_get_week_plan_scopes_by_date_range_and_user(self, conn, make_user):
        user_id = make_user()
        other_user = make_user()
        week_start = datetime.date(2026, 8, 24)

        in_week = plans_repo.create_plan_day(conn, user_id, week_start, "morning")
        plans_repo.create_plan_day(
            conn, user_id, week_start + datetime.timedelta(days=10), "morning"
        )
        plans_repo.create_plan_day(conn, other_user, week_start, "morning")

        week_plan = plans_repo.get_week_plan(conn, user_id, week_start)

        assert [p.id for p in week_plan] == [in_week.id]

    def test_grocery_snapshot_write_and_read_round_trip(self, conn, make_user):
        user_id = make_user()
        week_start = datetime.date(2026, 8, 24)
        ingredients = [{"ingredient_id": str(uuid.uuid4()), "name": "Onion"}]

        written = plans_repo.write_grocery_snapshot(conn, user_id, week_start, ingredients)
        assert written.ingredients == ingredients

        fetched = plans_repo.get_grocery_snapshot(conn, user_id, week_start)
        assert fetched is not None
        assert fetched.ingredients == ingredients

    def test_set_plan_skipped_toggles_the_flag(self, conn, make_user):
        user_id = make_user()
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 24), "night")
        assert plan.is_skipped is False

        skipped = plans_repo.set_plan_skipped(conn, plan.id, True)
        assert skipped.is_skipped is True

    def test_add_plan_item_supports_needs_manual_pick_with_no_dish(self, conn, make_user):
        """Technical spec §5.1 step 5's fallback state: zero eligible candidates even after
        relaxing the 10-day rule must surface as `needs_manual_pick`, never a blank/invented dish.
        """
        user_id = make_user()
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 24), "night")

        item = plans_repo.add_plan_item(
            conn, plan.id, "poriyal", None, status="needs_manual_pick"
        )

        assert item.status == "needs_manual_pick"
        assert item.dish_id is None

    def test_add_plan_item_rejects_needs_manual_pick_with_a_dish(self, conn, make_user):
        import pytest

        user_id = make_user()
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 24), "night")
        dish_id = _insert_dish(conn, name="Dish")

        with pytest.raises(ValueError):
            plans_repo.add_plan_item(conn, plan.id, "poriyal", dish_id, status="needs_manual_pick")

    def test_add_plan_item_rejects_filled_without_a_dish(self, conn, make_user):
        import pytest

        user_id = make_user()
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 24), "night")

        with pytest.raises(ValueError):
            plans_repo.add_plan_item(conn, plan.id, "poriyal", None)

    def test_resolve_manual_pick_fills_in_a_dish(self, conn, make_user):
        user_id = make_user()
        plan = plans_repo.create_plan_day(conn, user_id, datetime.date(2026, 8, 24), "night")
        item = plans_repo.add_plan_item(
            conn, plan.id, "poriyal", None, status="needs_manual_pick"
        )
        dish_id = _insert_dish(conn, name="Chosen Dish")

        resolved = plans_repo.resolve_manual_pick(conn, item.id, dish_id)

        assert resolved.status == "filled"
        assert resolved.dish_id == dish_id

    def test_grocery_snapshot_write_is_idempotent_per_week(self, conn, make_user):
        user_id = make_user()
        week_start = datetime.date(2026, 8, 24)

        plans_repo.write_grocery_snapshot(conn, user_id, week_start, [{"name": "First"}])
        plans_repo.write_grocery_snapshot(conn, user_id, week_start, [{"name": "Second"}])

        fetched = plans_repo.get_grocery_snapshot(conn, user_id, week_start)
        assert fetched is not None
        assert fetched.ingredients == [{"name": "Second"}]


class TestJobsRepository:
    def test_claim_or_create_job_is_idempotent(self, conn, make_user):
        user_id = make_user()
        week_start = datetime.date(2026, 8, 24)

        first = jobs_repo.claim_or_create_job(conn, user_id, week_start)
        second = jobs_repo.claim_or_create_job(conn, user_id, week_start)

        assert first.id == second.id
        assert first.status == "pending"

    def test_update_job_status_increments_attempts_and_sets_error(self, conn, make_user):
        user_id = make_user()
        job = jobs_repo.claim_or_create_job(conn, user_id, datetime.date(2026, 8, 24))

        updated = jobs_repo.update_job_status(
            conn, job.id, "failed", last_error="candidate pool empty", increment_attempt=True
        )

        assert updated.status == "failed"
        assert updated.attempts == 1
        assert updated.last_error == "candidate pool empty"

    def test_update_job_status_raises_for_unknown_job(self, conn):
        import pytest

        with pytest.raises(ValueError):
            jobs_repo.update_job_status(conn, uuid.uuid4(), "done")


class TestNotificationsRepository:
    def test_upsert_pending_is_idempotent_per_unique_constraint(self, conn, make_user):
        user_id = make_user()
        target_date = datetime.date(2026, 8, 24)

        first = notifications_repo.upsert_pending(conn, user_id, "daily_reminder", target_date)
        second = notifications_repo.upsert_pending(conn, user_id, "daily_reminder", target_date)

        assert first.id == second.id
        assert first.status == "pending"

    def test_mark_status_updates_status_and_ticket(self, conn, make_user):
        user_id = make_user()
        notification = notifications_repo.upsert_pending(
            conn, user_id, "daily_reminder", datetime.date(2026, 8, 24)
        )

        updated = notifications_repo.mark_status(
            conn, notification.id, "sent", expo_ticket_id="ticket-123", increment_attempt=True
        )

        assert updated.status == "sent"
        assert updated.expo_ticket_id == "ticket-123"
        assert updated.attempt == 1
        assert updated.delivered_at is None

    def test_mark_status_sets_delivered_at_only_on_the_delivered_transition(
        self, conn, make_user
    ):
        """Regression: migration 0008 added delivered_at specifically because updated_at doesn't
        change on UPDATE without a trigger, so mark_status must set it explicitly and atomically
        with the status transition (docs/MP-005) — not on every status change, only 'delivered'.
        """
        user_id = make_user()
        notification = notifications_repo.upsert_pending(
            conn, user_id, "daily_reminder", datetime.date(2026, 8, 24)
        )

        sent = notifications_repo.mark_status(conn, notification.id, "sent")
        assert sent.delivered_at is None

        delivered = notifications_repo.mark_status(conn, notification.id, "delivered")
        assert delivered.delivered_at is not None

    def test_list_for_target_date_scopes_by_type_and_date(self, conn, make_user):
        user_id = make_user()
        target_date = datetime.date(2026, 8, 24)
        notifications_repo.upsert_pending(conn, user_id, "daily_reminder", target_date)
        notifications_repo.upsert_pending(conn, user_id, "week_ready", target_date)

        results = notifications_repo.list_for_target_date(conn, "daily_reminder", target_date)

        assert len(results) == 1
        assert results[0].notification_type == "daily_reminder"
