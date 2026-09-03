"""MP-058/059/060/064: integration tests for the plan-item-edit Postgres RPCs
(supabase/migrations/0019_plan_item_edit_rpcs.sql), called the same way the mobile client does —
as the `authenticated` role with `auth.uid()` resolving via `request.jwt.claim.sub` — against a
real throwaway Postgres database built from the actual migrations (conftest.py).
"""

from __future__ import annotations

import datetime
import uuid

import psycopg
import pytest

_WEEK_START = datetime.date(2026, 8, 24)  # a Monday


def _dish(
    conn, name: str, *, item_type: str = "tiffin", diet: str = "veg", flags: list[str] | None = None
) -> uuid.UUID:
    row = conn.execute(
        "insert into dishes (name, item_type, veg_or_nonveg, dietary_flags, track_variety) "
        "values (%s, %s, %s, %s, true) returning id",
        (name, item_type, diet, flags or []),
    ).fetchone()
    return row["id"]


def _plan_item(conn, user_id, *, plan_date, item_type: str = "tiffin", dish_id=None) -> uuid.UUID:
    plan = conn.execute(
        "insert into meal_plans (user_id, plan_date, slot) values (%s, %s, 'morning') "
        "returning id",
        (user_id, plan_date),
    ).fetchone()
    item = conn.execute(
        "insert into plan_items (plan_id, item_type, dish_id, status) "
        "values (%s, %s, %s, 'filled') returning id",
        (plan["id"], item_type, dish_id),
    ).fetchone()
    return item["id"]


class TestSwapPlanItem:
    def test_swap_changes_only_the_targeted_item(self, conn, make_user, as_authenticated_user):
        user_id = make_user()
        old_dish = _dish(conn, "Old Tiffin")
        new_dish = _dish(conn, "New Tiffin")
        item_id = _plan_item(conn, user_id, plan_date=_WEEK_START, dish_id=old_dish)
        as_authenticated_user(user_id)

        result = conn.execute(
            "select dish_id, status from swap_plan_item(%s, %s)", (item_id, new_dish)
        ).fetchone()

        assert result["dish_id"] == new_dish
        assert result["status"] == "filled"

    def test_swap_rejects_a_different_item_type(self, conn, make_user, as_authenticated_user):
        user_id = make_user()
        tiffin_dish = _dish(conn, "A Tiffin", item_type="tiffin")
        rice_dish = _dish(conn, "A Rice", item_type="rice")
        item_id = _plan_item(conn, user_id, plan_date=_WEEK_START, dish_id=tiffin_dish)
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.Error, match="does not match slot item_type"):
            conn.execute("select swap_plan_item(%s, %s)", (item_id, rice_dish))

    def test_swap_hard_rejects_a_dietary_conflict_not_just_the_happy_path(
        self, conn, make_user, as_authenticated_user
    ):
        """MP-058's AC explicitly wants this proven, not just an unrestricted swap succeeding."""
        user_id = make_user()
        safe_dish = _dish(conn, "Safe Tiffin")
        unsafe_dish = _dish(conn, "Gluten Tiffin", flags=["Gluten"])
        conn.execute(
            "update user_profiles set dietary_restrictions = %s where id = %s",
            (["Gluten"], user_id),
        )
        item_id = _plan_item(conn, user_id, plan_date=_WEEK_START, dish_id=safe_dish)
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.errors.CheckViolation, match="dietary restrictions"):
            conn.execute("select swap_plan_item(%s, %s)", (item_id, unsafe_dish))

    def test_swap_resolves_a_needs_manual_pick_item(self, conn, make_user, as_authenticated_user):
        user_id = make_user()
        dish = _dish(conn, "Filled By Swap")
        plan = conn.execute(
            "insert into meal_plans (user_id, plan_date, slot) values (%s, %s, 'morning') "
            "returning id",
            (user_id, _WEEK_START),
        ).fetchone()
        item = conn.execute(
            "insert into plan_items (plan_id, item_type, dish_id, status) "
            "values (%s, 'tiffin', null, 'needs_manual_pick') returning id",
            (plan["id"],),
        ).fetchone()
        as_authenticated_user(user_id)

        result = conn.execute(
            "select dish_id, status from swap_plan_item(%s, %s)", (item["id"], dish)
        ).fetchone()

        assert (result["dish_id"], result["status"]) == (dish, "filled")

    def test_a_user_cannot_swap_another_users_plan_item(
        self, conn, make_user, as_authenticated_user
    ):
        owner = make_user()
        attacker = make_user()
        dish = _dish(conn, "Someone Elses Dish")
        other_dish = _dish(conn, "Attacker Supplied Dish")
        item_id = _plan_item(conn, owner, plan_date=_WEEK_START, dish_id=dish)
        as_authenticated_user(attacker)

        with pytest.raises(psycopg.Error, match="not found or not owned"):
            conn.execute("select swap_plan_item(%s, %s)", (item_id, other_dish))


class TestAddPlanItemToSlot:
    def test_add_inserts_a_new_item_in_the_slot(self, conn, make_user, as_authenticated_user):
        user_id = make_user()
        existing_dish = _dish(conn, "Existing")
        item_id = _plan_item(conn, user_id, plan_date=_WEEK_START, dish_id=existing_dish)
        plan_id = conn.execute(
            "select plan_id from plan_items where id = %s", (item_id,)
        ).fetchone()["plan_id"]
        new_dish = _dish(conn, "Added Snack", item_type="snack")
        as_authenticated_user(user_id)

        result = conn.execute(
            "select item_type, dish_id, status from add_plan_item_to_slot(%s, %s, %s)",
            (plan_id, "snack", new_dish),
        ).fetchone()

        assert (result["item_type"], result["dish_id"], result["status"]) == (
            "snack",
            new_dish,
            "filled",
        )

    def test_add_rejects_a_dish_whose_item_type_doesnt_match(
        self, conn, make_user, as_authenticated_user
    ):
        user_id = make_user()
        plan = conn.execute(
            "insert into meal_plans (user_id, plan_date, slot) values (%s, %s, 'afternoon') "
            "returning id",
            (user_id, _WEEK_START),
        ).fetchone()
        rice_dish = _dish(conn, "A Rice", item_type="rice")
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.Error, match="does not match requested item_type"):
            conn.execute(
                "select add_plan_item_to_slot(%s, %s, %s)", (plan["id"], "gravy", rice_dish)
            )

    def test_a_user_cannot_add_to_another_users_plan(self, conn, make_user, as_authenticated_user):
        owner = make_user()
        attacker = make_user()
        plan = conn.execute(
            "insert into meal_plans (user_id, plan_date, slot) values (%s, %s, 'morning') "
            "returning id",
            (owner, _WEEK_START),
        ).fetchone()
        dish = _dish(conn, "Attacker Dish")
        as_authenticated_user(attacker)

        with pytest.raises(psycopg.Error, match="not found or not owned"):
            conn.execute("select add_plan_item_to_slot(%s, %s, %s)", (plan["id"], "tiffin", dish))


class TestRemovePlanItem:
    def test_remove_deletes_the_item(self, conn, make_user, as_authenticated_user):
        user_id = make_user()
        dish = _dish(conn, "To Remove")
        item_id = _plan_item(conn, user_id, plan_date=_WEEK_START, dish_id=dish)
        as_authenticated_user(user_id)

        conn.execute("select remove_plan_item(%s)", (item_id,))

        remaining = conn.execute(
            "select count(*) as n from plan_items where id = %s", (item_id,)
        ).fetchone()
        assert remaining["n"] == 0

    def test_a_user_cannot_remove_another_users_plan_item(
        self, conn, make_user, as_authenticated_user
    ):
        owner = make_user()
        attacker = make_user()
        dish = _dish(conn, "Protected Dish")
        item_id = _plan_item(conn, owner, plan_date=_WEEK_START, dish_id=dish)
        as_authenticated_user(attacker)

        # A raised exception leaves the connection's transaction aborted until something rolls
        # back — conn.transaction() takes a savepoint here and rolls back only to it on the
        # propagated error, so the follow-up query below can still see the setup rows inserted
        # earlier in this same transaction (a plain conn.rollback() would discard those too).
        with pytest.raises(psycopg.Error, match="not found or not owned"), conn.transaction():
            conn.execute("select remove_plan_item(%s)", (item_id,))

        # The follow-up check must not run as the attacker: RLS itself hides the owner's row from
        # a different authenticated user (correct, separate defense-in-depth from the RPC's own
        # ownership check), which would make a still-attacker-scoped SELECT report 0 regardless of
        # whether the delete actually happened. Reset to this connection's original, unrestricted
        # role to check the row genuinely still exists.
        conn.execute("reset role")
        still_there = conn.execute(
            "select count(*) as n from plan_items where id = %s", (item_id,)
        ).fetchone()
        assert still_there["n"] == 1


class TestCarryOverPlanItem:
    def test_carry_over_copies_the_dish_and_marks_make_extra(
        self, conn, make_user, as_authenticated_user
    ):
        user_id = make_user()
        dish = _dish(conn, "Sambar", item_type="gravy")
        source_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="gravy", dish_id=dish
        )
        target_plan = conn.execute(
            "insert into meal_plans (user_id, plan_date, slot) values (%s, %s, 'night') "
            "returning id",
            (user_id, _WEEK_START),
        ).fetchone()
        as_authenticated_user(user_id)

        result = conn.execute(
            "select item_type, dish_id, status, make_extra from carry_over_plan_item(%s, %s)",
            (source_item, target_plan["id"]),
        ).fetchone()

        assert (result["item_type"], result["dish_id"], result["status"], result["make_extra"]) == (
            "gravy",
            dish,
            "filled",
            True,
        )

    def test_carry_over_from_a_needs_manual_pick_item_is_rejected(
        self, conn, make_user, as_authenticated_user
    ):
        user_id = make_user()
        plan = conn.execute(
            "insert into meal_plans (user_id, plan_date, slot) values (%s, %s, 'morning') "
            "returning id",
            (user_id, _WEEK_START),
        ).fetchone()
        source_item = conn.execute(
            "insert into plan_items (plan_id, item_type, dish_id, status) "
            "values (%s, 'tiffin', null, 'needs_manual_pick') returning id",
            (plan["id"],),
        ).fetchone()
        target_plan = conn.execute(
            "insert into meal_plans (user_id, plan_date, slot) values (%s, %s, 'night') "
            "returning id",
            (user_id, _WEEK_START),
        ).fetchone()
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.Error, match="not filled"):
            conn.execute(
                "select carry_over_plan_item(%s, %s)", (source_item["id"], target_plan["id"])
            )


class TestListSwapCandidates:
    def test_excludes_dishes_that_conflict_with_dietary_restrictions(
        self, conn, make_user, as_authenticated_user
    ):
        user_id = make_user()
        conn.execute(
            "update user_profiles set dietary_restrictions = %s where id = %s",
            (["Nuts"], user_id),
        )
        safe_dish = _dish(conn, "Safe Snack", item_type="snack")
        unsafe_dish = _dish(conn, "Nut Snack", item_type="snack", flags=["Nuts"])
        item_id = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="snack", dish_id=safe_dish
        )
        as_authenticated_user(user_id)

        candidates = {
            row["dish_id"]
            for row in conn.execute(
                "select dish_id from list_swap_candidates(%s)", (item_id,)
            ).fetchall()
        }

        assert safe_dish in candidates
        assert unsafe_dish not in candidates

    def test_flags_a_dish_already_used_elsewhere_this_week(
        self, conn, make_user, as_authenticated_user
    ):
        user_id = make_user()
        dish_a = _dish(conn, "Already This Week", item_type="snack")
        dish_b = _dish(conn, "Not Used", item_type="snack")
        # dish_a already placed on Tuesday of the same week
        _plan_item(
            conn,
            user_id,
            plan_date=_WEEK_START + datetime.timedelta(days=1),
            item_type="snack",
            dish_id=dish_a,
        )
        target_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="snack", dish_id=dish_b
        )
        as_authenticated_user(user_id)

        by_dish = {
            row["dish_id"]: row
            for row in conn.execute(
                "select dish_id, used_this_week from list_swap_candidates(%s)", (target_item,)
            ).fetchall()
        }

        assert by_dish[dish_a]["used_this_week"] is True
        assert by_dish[dish_b]["used_this_week"] is False

    def test_a_user_cannot_list_candidates_for_another_users_plan_item(
        self, conn, make_user, as_authenticated_user
    ):
        owner = make_user()
        attacker = make_user()
        dish = _dish(conn, "Private Item")
        item_id = _plan_item(conn, owner, plan_date=_WEEK_START, dish_id=dish)
        as_authenticated_user(attacker)

        with pytest.raises(psycopg.Error, match="not found or not owned"):
            conn.execute("select * from list_swap_candidates(%s)", (item_id,))
