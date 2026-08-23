-- Review fix (PR #1): 0006's `grant select, insert, update on user_profiles to authenticated`
-- plus the own-row RLS policy let any authenticated user run
--   update user_profiles set planning_mode = 'reserves' where id = auth.uid()
-- directly against PostgREST. Functional spec §2 makes `planning_mode` immutable after
-- onboarding — switching it changes which direction generation triggers run (technical spec §2.1)
-- and whether `available_ingredients` applies at all, and functional spec §2 explicitly defers
-- solving the transition questions (mid-week plan, accumulated data) rather than allowing a silent
-- switch. RLS policies only gate *rows*, not *columns* — the fix has to be a column-level
-- privilege, checked by Postgres independently of (and more restrictively than) the row policy.

revoke update on user_profiles from authenticated;

grant update (
  nonveg_days_per_week,
  nonveg_day_pattern,
  dietary_restrictions,
  dinner_style,
  grocery_day,
  timezone
) on user_profiles to authenticated;

-- `id` and `planning_mode` are deliberately excluded from the column grant above: `id` because
-- there is never a legitimate reason for a user to change it, `planning_mode` per the invariant
-- this migration exists to enforce. Only service_role (which bypasses grants and RLS both) can
-- change planning_mode — e.g. a future admin-mediated mode-switch flow, not a v1 requirement.
