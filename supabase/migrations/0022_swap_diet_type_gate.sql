-- Phase 8 (MP-024/025/026): mirrors backend/app/services/generation_eligibility.py's new
-- diet_type_allows hard gate into the swap RPCs (0019_plan_item_edit_rpcs.sql), same reasoning as
-- that file's own header comment for dietary_restrictions — this Python module only ever runs
-- inside scheduled batch jobs, never behind a live call the mobile client could reach, so the same
-- rule has to be reproduced in SQL for the edit-time path.
--
-- Scope decided with Pratheep this session: diet_type + meat_types are identity-level exclusions,
-- same footing as dietary_restrictions — hard-blocked here. egg_frequency's *day-based* permission
-- (any/specific/nonveg_days) stays advisory-only at edit time, same latitude the existing
-- exceeds_nonveg_quota advisory already has (a human editing is "the supervision" — functional
-- spec §6) — only the categorical 'never' case is covered below, since that's a diet-identity
-- statement ("no eggs, ever"), not a day-quota.

create or replace function dish_matches_diet_type(p_dish_id uuid, p_user_id uuid)
returns boolean
language sql
stable
as $$
  select
    case
      when d.veg_or_nonveg = 'veg' then true
      when up.diet_type = 'vegetarian' then false
      when 'Egg' = any(d.dietary_flags) then up.egg_frequency is distinct from 'never'
      when up.diet_type <> 'nonvegetarian' then false
      when up.meat_types = '{}' then true
      else d.meat_type = any(up.meat_types)
    end
  from dishes d, user_profiles up
  where d.id = p_dish_id and up.id = p_user_id;
$$;

revoke all on function dish_matches_diet_type(uuid, uuid) from public;

-- list_swap_candidates: add the hard diet-type filter alongside the existing dietary_restrictions
-- and dish_available_in_reserves checks.
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
    v_nonveg_quota is not null
      and d.veg_or_nonveg = 'nonveg'
      and not v_day_already_nonveg
      and v_week_nonveg_days >= v_nonveg_quota as exceeds_nonveg_quota
  from dishes d
  join user_profiles up on up.id = v_user_id
  where d.item_type = v_item_type
    and not (d.dietary_flags && up.dietary_restrictions)
    and dish_matches_diet_type(d.id, v_user_id)
    and dish_available_in_reserves(d.id, v_user_id, v_week_start)
  order by d.name;
end;
$$;

revoke all on function list_swap_candidates(uuid) from public;
grant execute on function list_swap_candidates(uuid) to authenticated;


-- swap_plan_item: add the same hard diet-type check as an explicit raise, mirroring the existing
-- dietary_restrictions block.
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
  if v_new_item_type <> v_item_type then
    raise exception 'dish item_type % does not match slot item_type %', v_new_item_type, v_item_type;
  end if;

  select dietary_restrictions into v_restrictions from user_profiles where id = v_user_id;
  if v_new_flags && v_restrictions then
    raise exception 'dish conflicts with dietary restrictions' using errcode = 'check_violation';
  end if;

  if not dish_matches_diet_type(new_dish_id, v_user_id) then
    raise exception 'dish does not match diet type or meat preference' using errcode = 'check_violation';
  end if;

  v_week_start := week_start_monday(v_plan_date);
  if not dish_available_in_reserves(new_dish_id, v_user_id, v_week_start) then
    raise exception 'dish is not available given this week''s Reserves ingredients'
      using errcode = 'check_violation';
  end if;

  update plan_items set dish_id = new_dish_id, status = 'filled'
  where id = target_plan_item_id
  returning * into v_result;

  return v_result;
end;
$$;

revoke all on function swap_plan_item(uuid, uuid) from public;
grant execute on function swap_plan_item(uuid, uuid) to authenticated;


-- add_plan_item_to_slot: same addition.
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

  if not dish_matches_diet_type(new_dish_id, v_user_id) then
    raise exception 'dish does not match diet type or meat preference' using errcode = 'check_violation';
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

-- remove_plan_item and carry_over_plan_item are unchanged (carry_over_plan_item deliberately
-- bypasses every gate by design, per 0019's own comment — not touched here).
