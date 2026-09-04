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


def _plan_item(
    conn, user_id, *, plan_date, item_type: str = "tiffin", dish_id=None, slot: str = "morning"
) -> uuid.UUID:
    plan = conn.execute(
        "insert into meal_plans (user_id, plan_date, slot) values (%s, %s, %s) returning id",
        (user_id, plan_date, slot),
    ).fetchone()
    item = conn.execute(
        "insert into plan_items (plan_id, item_type, dish_id, status) "
        "values (%s, %s, %s, 'filled') returning id",
        (plan["id"], item_type, dish_id),
    ).fetchone()
    return item["id"]


def _plan_for_slot(conn, user_id, *, plan_date, slot: str) -> uuid.UUID:
    plan = conn.execute(
        "insert into meal_plans (user_id, plan_date, slot) values (%s, %s, %s) returning id",
        (user_id, plan_date, slot),
    ).fetchone()
    return plan["id"]


def _reserves_unavailable_dish(conn, user_id, *, item_type: str = "gravy") -> uuid.UUID:
    """A dish needing a non-staple ingredient the user hasn't marked available for `week_start` —
    for Reserves-eligibility tests. Switches the user to reserves mode as a side effect.
    """
    conn.execute(
        "update user_profiles set planning_mode = 'reserves' where id = %s", (user_id,)
    )
    dish_id = _dish(conn, "Needs Fresh Fish", item_type=item_type)
    ingredient = conn.execute(
        "insert into ingredients (canonical_name, is_staple) values ('Fresh Fish', false) "
        "returning id"
    ).fetchone()
    conn.execute(
        "insert into dish_ingredients (dish_id, ingredient_id) values (%s, %s)",
        (dish_id, ingredient["id"]),
    )
    return dish_id


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

    def test_swap_rejects_a_dish_unavailable_in_reserves_mode_via_a_direct_rpc_call(
        self, conn, make_user, as_authenticated_user
    ):
        """PR review fix: list_swap_candidates already filtered Reserves-unavailable dishes out of
        the candidate list, but swap_plan_item itself never checked — a Reserves user calling the
        RPC directly with a hand-picked new_dish_id (not one the UI ever offered) could put an
        unavailable dish into their plan anyway. This calls swap_plan_item exactly that way.
        """
        user_id = make_user()
        safe_dish = _dish(conn, "Pantry Curry", item_type="gravy")
        item_id = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="gravy", dish_id=safe_dish
        )
        unavailable_dish = _reserves_unavailable_dish(conn, user_id, item_type="gravy")
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.errors.CheckViolation, match="Reserves"):
            conn.execute("select swap_plan_item(%s, %s)", (item_id, unavailable_dish))


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

    def test_add_rejects_an_item_type_the_slot_already_has(
        self, conn, make_user, as_authenticated_user
    ):
        """PR review fix (MP-060 AC): add is for a *missing* item type only — a second ordinary
        rice item in a slot that already has one isn't 'add a missing item', it's a silent
        duplicate. carry_over_plan_item is the separate, intentional path for a type-duplicate.
        """
        user_id = make_user()
        existing_dish = _dish(conn, "Existing Rice", item_type="rice")
        item_id = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="rice", dish_id=existing_dish
        )
        plan_id = conn.execute(
            "select plan_id from plan_items where id = %s", (item_id,)
        ).fetchone()["plan_id"]
        second_rice = _dish(conn, "Second Rice", item_type="rice")
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.errors.CheckViolation, match="already has a rice item"):
            conn.execute(
                "select add_plan_item_to_slot(%s, %s, %s)", (plan_id, "rice", second_rice)
            )

    def test_add_rejects_a_dish_unavailable_in_reserves_mode_via_a_direct_rpc_call(
        self, conn, make_user, as_authenticated_user
    ):
        """PR review fix: same direct-RPC Reserves bypass as swap_plan_item, but for add."""
        user_id = make_user()
        plan_id = _plan_for_slot(conn, user_id, plan_date=_WEEK_START, slot="afternoon")
        unavailable_dish = _reserves_unavailable_dish(conn, user_id, item_type="gravy")
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.errors.CheckViolation, match="Reserves"):
            conn.execute(
                "select add_plan_item_to_slot(%s, %s, %s)", (plan_id, "gravy", unavailable_dish)
            )


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
        """functional spec §6.3's own example — bulk-cooked sambar reused for lunch and dinner —
        is a same-day, next-slot carry: 'afternoon' (lunch) into 'snack_2' (the next chronological
        slot after afternoon), not an arbitrary later slot.
        """
        user_id = make_user()
        dish = _dish(conn, "Sambar", item_type="gravy")
        source_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="gravy", dish_id=dish, slot="afternoon"
        )
        target_plan = _plan_for_slot(conn, user_id, plan_date=_WEEK_START, slot="snack_2")
        as_authenticated_user(user_id)

        result = conn.execute(
            "select item_type, dish_id, status, make_extra from carry_over_plan_item(%s, %s)",
            (source_item, target_plan),
        ).fetchone()

        assert (result["item_type"], result["dish_id"], result["status"], result["make_extra"]) == (
            "gravy",
            dish,
            "filled",
            True,
        )

    def test_carry_over_into_the_same_slot_is_rejected(
        self, conn, make_user, as_authenticated_user
    ):
        """PR review fix: carrying into the source's own plan (same slot) would silently duplicate
        the item type within one slot — not what 'make extra for later' means.
        """
        user_id = make_user()
        dish = _dish(conn, "Sambar", item_type="gravy")
        source_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="gravy", dish_id=dish, slot="afternoon"
        )
        source_plan_id = conn.execute(
            "select plan_id from plan_items where id = %s", (source_item,)
        ).fetchone()["plan_id"]
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.errors.CheckViolation, match="next slot of the same day"):
            conn.execute(
                "select carry_over_plan_item(%s, %s)", (source_item, source_plan_id)
            )

    def test_carry_over_backward_into_an_earlier_slot_is_rejected(
        self, conn, make_user, as_authenticated_user
    ):
        """PR review fix: Night -> Morning must not be allowed just because both slots are the
        same day — carry-over only ever moves forward, to the very next slot.
        """
        user_id = make_user()
        dish = _dish(conn, "Sambar", item_type="gravy")
        source_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="gravy", dish_id=dish, slot="night"
        )
        earlier_plan = _plan_for_slot(conn, user_id, plan_date=_WEEK_START, slot="morning")
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.errors.CheckViolation, match="next slot of the same day"):
            conn.execute("select carry_over_plan_item(%s, %s)", (source_item, earlier_plan))

    def test_carry_over_into_a_non_adjacent_later_slot_is_rejected(
        self, conn, make_user, as_authenticated_user
    ):
        """Skipping a slot (morning -> afternoon, past snack_1) is still not *the* next slot."""
        user_id = make_user()
        dish = _dish(conn, "Idli", item_type="tiffin")
        source_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="tiffin", dish_id=dish, slot="morning"
        )
        skip_ahead_plan = _plan_for_slot(conn, user_id, plan_date=_WEEK_START, slot="afternoon")
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.errors.CheckViolation, match="next slot of the same day"):
            conn.execute("select carry_over_plan_item(%s, %s)", (source_item, skip_ahead_plan))

    def test_carry_over_into_the_next_days_slot_is_rejected(
        self, conn, make_user, as_authenticated_user
    ):
        """Night is the day's last slot — there is no next slot, same day or otherwise; carrying
        into tomorrow's morning must not be treated as a valid 'next slot'.
        """
        user_id = make_user()
        dish = _dish(conn, "Sambar", item_type="gravy")
        source_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="gravy", dish_id=dish, slot="night"
        )
        next_day_morning = _plan_for_slot(
            conn, user_id, plan_date=_WEEK_START + datetime.timedelta(days=1), slot="morning"
        )
        as_authenticated_user(user_id)

        with pytest.raises(psycopg.errors.CheckViolation, match="next slot of the same day"):
            conn.execute("select carry_over_plan_item(%s, %s)", (source_item, next_day_morning))

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

    def test_excludes_a_dish_unavailable_in_reserves_mode(
        self, conn, make_user, as_authenticated_user
    ):
        user_id = make_user()
        safe_dish = _dish(conn, "Pantry Curry", item_type="gravy")
        item_id = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="gravy", dish_id=safe_dish
        )
        unavailable_dish = _reserves_unavailable_dish(conn, user_id, item_type="gravy")
        as_authenticated_user(user_id)

        candidates = {
            row["dish_id"]
            for row in conn.execute(
                "select dish_id from list_swap_candidates(%s)", (item_id,)
            ).fetchall()
        }

        assert safe_dish in candidates
        assert unavailable_dish not in candidates

    def test_flags_a_candidate_that_would_exceed_the_nonveg_quota(
        self, conn, make_user, as_authenticated_user
    ):
        """MP-062 PR review fix: list_swap_candidates previously exposed only used_this_week /
        used_recently, so the UI had no way to warn about a non-veg edit exceeding the weekly
        quota. A candidate is flagged when picking it would make this day a *new* non-veg day
        while the week has already used up its non-veg-day quota elsewhere.
        """
        user_id = make_user()
        conn.execute(
            "update user_profiles set nonveg_days_per_week = 1 where id = %s", (user_id,)
        )
        already_nonveg_dish = _dish(conn, "Already Nonveg Day", item_type="gravy", diet="nonveg")
        _plan_item(
            conn,
            user_id,
            plan_date=_WEEK_START + datetime.timedelta(days=1),
            item_type="gravy",
            dish_id=already_nonveg_dish,
        )
        veg_target_dish = _dish(conn, "Veg Snack", item_type="snack")
        target_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="snack", dish_id=veg_target_dish
        )
        nonveg_candidate = _dish(conn, "Nonveg Snack", item_type="snack", diet="nonveg")
        veg_candidate = _dish(conn, "Veg Snack Two", item_type="snack")
        as_authenticated_user(user_id)

        by_dish = {
            row["dish_id"]: row
            for row in conn.execute(
                "select dish_id, exceeds_nonveg_quota from list_swap_candidates(%s)", (target_item,)
            ).fetchall()
        }

        assert by_dish[nonveg_candidate]["exceeds_nonveg_quota"] is True
        assert by_dish[veg_candidate]["exceeds_nonveg_quota"] is False

    def test_a_candidate_that_would_only_match_the_days_own_existing_nonveg_item_is_not_flagged(
        self, conn, make_user, as_authenticated_user
    ):
        """Swapping *within* an already-non-veg day doesn't add a new non-veg day, so it must
        never be flagged even at quota — this is what actually distinguishes the check from a
        blanket 'week is at quota' warning.
        """
        user_id = make_user()
        conn.execute(
            "update user_profiles set nonveg_days_per_week = 1 where id = %s", (user_id,)
        )
        other_nonveg_dish = _dish(conn, "Other Nonveg Item", item_type="gravy", diet="nonveg")
        _plan_item(
            conn,
            user_id,
            plan_date=_WEEK_START,
            item_type="gravy",
            dish_id=other_nonveg_dish,
        )
        target_dish = _dish(conn, "Snack Slot", item_type="snack")
        target_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="snack", dish_id=target_dish
        )
        nonveg_candidate = _dish(conn, "Nonveg Snack", item_type="snack", diet="nonveg")
        as_authenticated_user(user_id)

        row = conn.execute(
            "select exceeds_nonveg_quota from list_swap_candidates(%s) where dish_id = %s",
            (target_item, nonveg_candidate),
        ).fetchone()

        assert row["exceeds_nonveg_quota"] is False

    def test_swap_succeeds_even_when_the_candidate_exceeds_the_nonveg_quota_advisory_only(
        self, conn, make_user, as_authenticated_user
    ):
        """Edit-time rules are advisory only (functional spec §6) — exceeds_nonveg_quota must
        never block the underlying swap, only inform it.
        """
        user_id = make_user()
        conn.execute(
            "update user_profiles set nonveg_days_per_week = 1 where id = %s", (user_id,)
        )
        already_nonveg_dish = _dish(conn, "Already Nonveg Day", item_type="gravy", diet="nonveg")
        _plan_item(
            conn,
            user_id,
            plan_date=_WEEK_START + datetime.timedelta(days=1),
            item_type="gravy",
            dish_id=already_nonveg_dish,
        )
        veg_target_dish = _dish(conn, "Veg Snack", item_type="snack")
        target_item = _plan_item(
            conn, user_id, plan_date=_WEEK_START, item_type="snack", dish_id=veg_target_dish
        )
        nonveg_candidate = _dish(conn, "Nonveg Snack", item_type="snack", diet="nonveg")
        as_authenticated_user(user_id)

        result = conn.execute(
            "select dish_id from swap_plan_item(%s, %s)", (target_item, nonveg_candidate)
        ).fetchone()

        assert result["dish_id"] == nonveg_candidate
