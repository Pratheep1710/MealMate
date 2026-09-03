-- MP-063: enforce the 5-8 favorites cap (docs/version1_mealPlanner_technical.md's decision log:
-- "Unbounded favorites would let the variety guarantee degenerate entirely") at the row level, not
-- just in application code. `user_favorite_dishes` already grants direct `insert` to `authenticated`
-- scoped by `user_id = auth.uid()` (0006) — the mobile client can and will insert directly, the
-- same way it already does for meal_plans.is_skipped, so a Python-layer check alone (which nothing
-- on the live client path ever calls) would not actually hold the line. A trigger enforces it
-- regardless of which path (direct client insert, a future RPC, an admin script) adds the row.
--
-- 8 is the enforced ceiling — the upper end of the documented 5-8 estimate range, chosen because
-- the range itself is framed as "at most this many before variety degrades," not a recommended
-- default; the app layer is free to nudge the user to stop adding favorites earlier than 8.
create or replace function enforce_favorites_cap()
returns trigger
language plpgsql
as $$
declare
  existing_count int;
  favorites_cap constant int := 8;
begin
  -- Re-adding an already-favorited dish resolves via the caller's ON CONFLICT DO NOTHING, but
  -- that resolution happens *after* a BEFORE INSERT trigger runs — from here, a re-add and a
  -- genuinely new favorite look identical unless checked explicitly. Without this, a user already
  -- at the cap couldn't even no-op re-favorite something they already have.
  if exists (
    select 1 from user_favorite_dishes
    where user_id = new.user_id and dish_id = new.dish_id
  ) then
    return new;
  end if;

  select count(*) into existing_count
  from user_favorite_dishes
  where user_id = new.user_id;

  if existing_count >= favorites_cap then
    raise exception 'favorites cap of % reached for user %', favorites_cap, new.user_id
      using errcode = 'check_violation';
  end if;

  return new;
end;
$$;

create trigger user_favorite_dishes_enforce_cap
  before insert on user_favorite_dishes
  for each row
  execute function enforce_favorites_cap();
