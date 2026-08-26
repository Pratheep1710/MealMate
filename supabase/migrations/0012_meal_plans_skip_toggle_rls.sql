-- MP-061: skip/eating-out toggle write path.
-- Source: docs/MP-001's "skip/eating-out toggle" (functional spec §6). `meal_plans.is_skipped`
-- (0007) and its downstream exclusion (app/repositories/history.py's get_recent_variety_dish_ids)
-- already existed, but 0006 only granted `select` on meal_plans to `authenticated` — every edit in
-- this app autosaves as a direct RLS-scoped client write (same pattern as plan_items' full CRUD
-- grant in 0006), so the toggle needs its own narrow write grant, not a backend route.
--
-- Column-level grant (same technique as 0009's planning_mode lockdown, used here to permit rather
-- than restrict) limits the client to flipping is_skipped only — plan_date/slot/user_id stay
-- immutable from this policy's perspective.

grant update (is_skipped) on meal_plans to authenticated;

create policy meal_plans_update_own_skip on meal_plans
  for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
