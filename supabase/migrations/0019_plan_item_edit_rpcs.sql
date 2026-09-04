-- MP-058/059/060/064: item-level plan editing RPCs (functional spec §6's swap/add/remove, and
-- §4 item 3's make_extra carry-over). 0006's RLS policies already grant `plan_items` full CRUD to
-- the owning user via the `meal_plans` join, so a raw client write is *possible* — these functions
-- exist for the same reason register_push_token/unregister_push_token do (0013/0014): the write
-- needs validation a plain RLS-scoped statement can't express (item_type match, dietary safety,
-- Reserves ingredient availability), and technical spec §3's own table lists quick-swap explicitly
-- as "Postgres RPC / stored function — no LLM call, no Python hop", not a live backend endpoint
-- (none exists for this path).
--
-- Dietary safety is the one hard gate reproduced here, matching
-- backend/app/services/generation_eligibility.py's array-overlap rule exactly (dietary_flags &&
-- dietary_restrictions -> reject) — same rule, expressed in SQL because that Python module only
-- ever runs inside scheduled batch jobs, never behind a live call the mobile client could reach.
-- Reserves availability is the second hard gate — see dish_available_in_reserves below, called from
-- every function that can put an unavailable dish into a Reserves user's plan (PR review fix: this
-- was previously only checked in list_swap_candidates, so a direct RPC call with a hand-picked
-- new_dish_id could bypass it entirely).
-- In-week/10-day repeat and non-veg quota are deliberately NOT enforced here: edit-time rules are
-- advisory only (functional spec §6 — "A human explicitly choosing something is the supervision"),
-- surfaced instead by MP-062's dismissible indicators (list_swap_candidates below), never blocking
-- a save.

-- PR review fix: centralizes the Monday-of-week computation so list/swap/add/carry-over can't
-- silently drift apart on it. dow: 0=Sunday..6=Saturday, so (dow + 6) % 7 is the number of days
-- since that week's Monday for every day including Sunday itself.
create or replace function week_start_monday(p_date date)
returns date
language sql
immutable
as $$
  select p_date - ((extract(dow from p_date)::int + 6) % 7);
$$;

-- Never called directly by the client — only from inside the SECURITY DEFINER functions below,
-- which retain their owner's implicit execute rights regardless of this revoke. Postgres grants
-- EXECUTE to PUBLIC on new functions by default; revoked here to match this file's other RPCs'
-- explicit posture rather than leaving an unused grant in place.
revoke all on function week_start_monday(date) from public;

-- PR review fix: the single Reserves-availability predicate — a dish is ineligible for a Reserves
-- user if it needs any non-staple ingredient the user hasn't marked available for the target week.
-- Suggestion-mode users always pass (the whole check is a no-op for them). Called from list, swap,
-- and add, so a direct RPC call can no longer put an unavailable dish into a Reserves user's plan
-- just because it skips the candidate-listing step.
create or replace function dish_available_in_reserves(p_dish_id uuid, p_user_id uuid, p_week_start date)
returns boolean
language sql
stable
as $$
  select
    up.planning_mode <> 'reserves'
    or not exists (
      select 1
      from dish_ingredients di
      join ingredients i on i.id = di.ingredient_id
      where di.dish_id = p_dish_id
        and i.is_staple = false
        and not exists (
          select 1 from available_ingredients ai
          where ai.user_id = p_user_id
            and ai.week_start = p_week_start
            and ai.ingredient_id = di.ingredient_id
        )
    )
  from user_profiles up
  where up.id = p_user_id;
$$;

revoke all on function dish_available_in_reserves(uuid, uuid, date) from public;

-- PR review fix: chronological order of a day's six slots, matching
-- mobile/src/screens/weekPlan/rollingDays.ts's CHRONOLOGICAL_SLOTS (sorted by real clock time, not
-- the DB enum's declaration order) — the single source of truth carry_over_plan_item uses to derive
-- "the next slot".
create or replace function plan_slot_order(p_slot text)
returns int
language sql
immutable
as $$
  select case p_slot
    when 'morning' then 1
    when 'snack_1' then 2
    when 'afternoon' then 3
    when 'snack_2' then 4
    when 'night' then 5
    when 'snack_3' then 6
  end;
$$;

revoke all on function plan_slot_order(text) from public;


create or replace function list_swap_candidates(target_plan_item_id uuid)
returns table (
  dish_id uuid,
  name text,
  veg_or_nonveg text,
  prep_minutes int,
  track_variety boolean,
  used_this_week boolean,
  used_recently boolean,
  exceeds_nonveg_quota boolean
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_item_type text;
  v_plan_date date;
  v_user_id uuid;
  v_week_start date;
  v_week_end date;
  v_nonveg_quota int;
  v_day_already_nonveg boolean;
  v_week_nonveg_days int;
begin
  select pi.item_type, mp.plan_date, mp.user_id
    into v_item_type, v_plan_date, v_user_id
  from plan_items pi
  join meal_plans mp on mp.id = pi.plan_id
  where pi.id = target_plan_item_id and mp.user_id = auth.uid();

  if v_item_type is null then
    raise exception 'plan item not found or not owned by the current user';
  end if;

  v_week_start := week_start_monday(v_plan_date);
  v_week_end := v_week_start + 6;

  select up.nonveg_days_per_week into v_nonveg_quota
  from user_profiles up where up.id = v_user_id;

  -- MP-062 quota advisory (PR review fix): does v_plan_date already have a non-veg item other than
  -- the one being replaced, and how many distinct days this week already do — both computed once
  -- here rather than per-candidate, since neither depends on the candidate dish.
  select exists (
    select 1
    from plan_items pi4
    join meal_plans mp4 on mp4.id = pi4.plan_id
    join dishes d4 on d4.id = pi4.dish_id
    where mp4.user_id = v_user_id
      and mp4.plan_date = v_plan_date
      and mp4.is_skipped = false
      and pi4.status = 'filled'
      and d4.veg_or_nonveg = 'nonveg'
      and pi4.id <> target_plan_item_id
  ) into v_day_already_nonveg;

  select count(distinct mp5.plan_date) into v_week_nonveg_days
  from plan_items pi5
  join meal_plans mp5 on mp5.id = pi5.plan_id
  join dishes d5 on d5.id = pi5.dish_id
  where mp5.user_id = v_user_id
    and mp5.plan_date between v_week_start and v_week_end
    and mp5.is_skipped = false
    and pi5.status = 'filled'
    and d5.veg_or_nonveg = 'nonveg'
    and pi5.id <> target_plan_item_id;

  return query
  select
    d.id,
    d.name,
    d.veg_or_nonveg,
    d.prep_minutes,
    d.track_variety,
    exists (
      select 1
      from plan_items pi2
      join meal_plans mp2 on mp2.id = pi2.plan_id
      where mp2.user_id = v_user_id
        and mp2.plan_date between v_week_start and v_week_end
        and mp2.is_skipped = false
        and pi2.status = 'filled'
        and pi2.dish_id = d.id
        and pi2.id <> target_plan_item_id
    ) as used_this_week,
    -- Mirrors MP-035's 10-day exclusion set exactly: track_variety dishes only, favorites exempt.
    d.track_variety
      and not exists (
        select 1 from user_favorite_dishes ufd
        where ufd.user_id = v_user_id and ufd.dish_id = d.id
      )
      and exists (
        select 1
        from plan_items pi3
        join meal_plans mp3 on mp3.id = pi3.plan_id
        where mp3.user_id = v_user_id
          and mp3.plan_date >= v_plan_date - 10
          and mp3.plan_date < v_plan_date
          and mp3.is_skipped = false
          and pi3.status = 'filled'
          and pi3.dish_id = d.id
      ) as used_recently,
    -- True when picking this dish would make v_plan_date a *new* non-veg day (it isn't one
    -- already) while the week has already used up its non-veg-day quota. Advisory only — never
    -- filters a candidate out, surfaced as a dismissible badge (MP-062).
    v_nonveg_quota is not null
      and d.veg_or_nonveg = 'nonveg'
      and not v_day_already_nonveg
      and v_week_nonveg_days >= v_nonveg_quota as exceeds_nonveg_quota
  from dishes d
  join user_profiles up on up.id = v_user_id
  where d.item_type = v_item_type
    and not (d.dietary_flags && up.dietary_restrictions)
    and dish_available_in_reserves(d.id, v_user_id, v_week_start)
  order by d.name;
end;
$$;

revoke all on function list_swap_candidates(uuid) from public;
grant execute on function list_swap_candidates(uuid) to authenticated;


create or replace function swap_plan_item(target_plan_item_id uuid, new_dish_id uuid)
returns plan_items
language plpgsql
security definer
set search_path = public
as $$
declare
  v_item_type text;
  v_user_id uuid;
  v_plan_date date;
  v_week_start date;
  v_new_item_type text;
  v_new_flags text[];
  v_restrictions text[];
  v_result plan_items;
begin
  select pi.item_type, mp.user_id, mp.plan_date into v_item_type, v_user_id, v_plan_date
  from plan_items pi
  join meal_plans mp on mp.id = pi.plan_id
  where pi.id = target_plan_item_id and mp.user_id = auth.uid();

  if v_item_type is null then
    raise exception 'plan item not found or not owned by the current user';
  end if;

  select item_type, dietary_flags into v_new_item_type, v_new_flags
  from dishes where id = new_dish_id;

  if v_new_item_type is null then
    raise exception 'dish % not found', new_dish_id;
  end if;
  -- MP-058 AC: swap changes exactly one item and preserves slot structure.
  if v_new_item_type <> v_item_type then
    raise exception 'dish item_type % does not match slot item_type %', v_new_item_type, v_item_type;
  end if;

  select dietary_restrictions into v_restrictions from user_profiles where id = v_user_id;
  if v_new_flags && v_restrictions then
    raise exception 'dish conflicts with dietary restrictions' using errcode = 'check_violation';
  end if;

  v_week_start := week_start_monday(v_plan_date);
  if not dish_available_in_reserves(new_dish_id, v_user_id, v_week_start) then
    raise exception 'dish is not available given this week''s Reserves ingredients'
      using errcode = 'check_violation';
  end if;

  -- Setting status = 'filled' unconditionally also resolves a needs_manual_pick item the same
  -- way — swapping in a valid dish is exactly what resolving one means, no special case needed.
  update plan_items set dish_id = new_dish_id, status = 'filled'
  where id = target_plan_item_id
  returning * into v_result;

  return v_result;
end;
$$;

revoke all on function swap_plan_item(uuid, uuid) from public;
grant execute on function swap_plan_item(uuid, uuid) to authenticated;


create or replace function add_plan_item_to_slot(
  target_plan_id uuid, new_item_type text, new_dish_id uuid
)
returns plan_items
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid;
  v_plan_date date;
  v_week_start date;
  v_dish_item_type text;
  v_dish_flags text[];
  v_restrictions text[];
  v_result plan_items;
begin
  select user_id, plan_date into v_user_id, v_plan_date from meal_plans
  where id = target_plan_id and user_id = auth.uid();

  if v_user_id is null then
    raise exception 'meal plan not found or not owned by the current user';
  end if;

  -- PR review fix (MP-060 AC): add is for a *missing* item type only — a second item of a type
  -- already in this slot is either a mistake or, if intentional, exactly what carry_over_plan_item
  -- (make_extra) exists for, which goes through its own dietary-bypass-by-design path deliberately.
  if exists (
    select 1 from plan_items where plan_id = target_plan_id and item_type = new_item_type
  ) then
    raise exception 'slot already has a % item; use swap or make-extra instead', new_item_type
      using errcode = 'check_violation';
  end if;

  select item_type, dietary_flags into v_dish_item_type, v_dish_flags
  from dishes where id = new_dish_id;

  if v_dish_item_type is null then
    raise exception 'dish % not found', new_dish_id;
  end if;
  if v_dish_item_type <> new_item_type then
    raise exception 'dish item_type % does not match requested item_type %',
      v_dish_item_type, new_item_type;
  end if;

  select dietary_restrictions into v_restrictions from user_profiles where id = v_user_id;
  if v_dish_flags && v_restrictions then
    raise exception 'dish conflicts with dietary restrictions' using errcode = 'check_violation';
  end if;

  v_week_start := week_start_monday(v_plan_date);
  if not dish_available_in_reserves(new_dish_id, v_user_id, v_week_start) then
    raise exception 'dish is not available given this week''s Reserves ingredients'
      using errcode = 'check_violation';
  end if;

  insert into plan_items (plan_id, item_type, dish_id, status)
  values (target_plan_id, new_item_type, new_dish_id, 'filled')
  returning * into v_result;

  return v_result;
end;
$$;

revoke all on function add_plan_item_to_slot(uuid, text, uuid) from public;
grant execute on function add_plan_item_to_slot(uuid, text, uuid) to authenticated;


create or replace function remove_plan_item(target_plan_item_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from plan_items pi
  using meal_plans mp
  where pi.id = target_plan_item_id
    and pi.plan_id = mp.id
    and mp.user_id = auth.uid();

  if not found then
    raise exception 'plan item not found or not owned by the current user';
  end if;
end;
$$;

revoke all on function remove_plan_item(uuid) from public;
grant execute on function remove_plan_item(uuid) to authenticated;


-- MP-064: make-extra carry-over. The dish is already planned (and was already dietary/Reserves
-- checked when it was originally placed), so this deliberately does not re-run either gate — it
-- copies a known-safe dish_id forward, not a new choice. Deliberately bypasses in-week and 10-day
-- repeat handling by design (technical spec §4 item 3: "deliberately bypassing the no-repeat rule.
-- One boolean on the plan entry") — `make_extra = true` is what distinguishes this from an
-- accidental duplicate for every downstream reader (variety history, edit-time indicators).
--
-- PR review fix (functional spec §6.3's own example, "bulk-cooked sambar reused for lunch and
-- dinner"): the target must be *the* next chronological slot of the same day, not any slot the
-- caller names — otherwise this both duplicates within a slot (Morning -> Morning) and carries
-- backward (Night -> Morning), neither of which is "make extra for later", it's just a second copy.
create or replace function carry_over_plan_item(source_plan_item_id uuid, target_plan_id uuid)
returns plan_items
language plpgsql
security definer
set search_path = public
as $$
declare
  v_source_user_id uuid;
  v_source_plan_date date;
  v_source_slot text;
  v_item_type text;
  v_dish_id uuid;
  v_target_user_id uuid;
  v_target_plan_date date;
  v_target_slot text;
  v_result plan_items;
begin
  select mp.user_id, mp.plan_date, mp.slot, pi.item_type, pi.dish_id
    into v_source_user_id, v_source_plan_date, v_source_slot, v_item_type, v_dish_id
  from plan_items pi
  join meal_plans mp on mp.id = pi.plan_id
  where pi.id = source_plan_item_id and mp.user_id = auth.uid() and pi.status = 'filled';

  if v_source_user_id is null then
    raise exception 'source plan item not found, not owned by the current user, or not filled';
  end if;

  select user_id, plan_date, slot into v_target_user_id, v_target_plan_date, v_target_slot
  from meal_plans
  where id = target_plan_id and user_id = auth.uid();

  if v_target_user_id is null then
    raise exception 'target meal plan not found or not owned by the current user';
  end if;

  if v_target_plan_date <> v_source_plan_date
     or plan_slot_order(v_target_slot) <> plan_slot_order(v_source_slot) + 1 then
    raise exception 'make-extra can only carry into the next slot of the same day'
      using errcode = 'check_violation';
  end if;

  insert into plan_items (plan_id, item_type, dish_id, status, make_extra)
  values (target_plan_id, v_item_type, v_dish_id, 'filled', true)
  returning * into v_result;

  return v_result;
end;
$$;

revoke all on function carry_over_plan_item(uuid, uuid) from public;
grant execute on function carry_over_plan_item(uuid, uuid) to authenticated;
