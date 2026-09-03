-- MP-058/059/060/064: item-level plan editing RPCs (functional spec §6's swap/add/remove, and
-- §4 item 3's make_extra carry-over). 0006's RLS policies already grant `plan_items` full CRUD to
-- the owning user via the `meal_plans` join, so a raw client write is *possible* — these functions
-- exist for the same reason register_push_token/unregister_push_token do (0013/0014): the write
-- needs validation a plain RLS-scoped statement can't express (item_type match, dietary safety),
-- and technical spec §3's own table lists quick-swap explicitly as "Postgres RPC / stored function
-- — no LLM call, no Python hop", not a live backend endpoint (none exists for this path).
--
-- Dietary safety is the one hard gate reproduced here, matching
-- backend/app/services/generation_eligibility.py's array-overlap rule exactly (dietary_flags &&
-- dietary_restrictions -> reject) — same rule, expressed in SQL because that Python module only
-- ever runs inside scheduled batch jobs, never behind a live call the mobile client could reach.
-- In-week/10-day repeat and non-veg quota are deliberately NOT enforced here: edit-time rules are
-- advisory only (functional spec §6 — "A human explicitly choosing something is the supervision"),
-- surfaced instead by MP-062's dismissible indicators (list_swap_candidates below), never blocking
-- a save.

create or replace function list_swap_candidates(target_plan_item_id uuid)
returns table (
  dish_id uuid,
  name text,
  veg_or_nonveg text,
  prep_minutes int,
  track_variety boolean,
  used_this_week boolean,
  used_recently boolean
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
begin
  select pi.item_type, mp.plan_date, mp.user_id
    into v_item_type, v_plan_date, v_user_id
  from plan_items pi
  join meal_plans mp on mp.id = pi.plan_id
  where pi.id = target_plan_item_id and mp.user_id = auth.uid();

  if v_item_type is null then
    raise exception 'plan item not found or not owned by the current user';
  end if;

  -- Monday of plan_date's week: extract(dow) is 0=Sunday..6=Saturday, so (dow + 6) % 7 is the
  -- number of days since that week's Monday for every day including Sunday itself.
  v_week_start := v_plan_date - ((extract(dow from v_plan_date)::int + 6) % 7);
  v_week_end := v_week_start + 6;

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
      ) as used_recently
  from dishes d
  join user_profiles up on up.id = v_user_id
  where d.item_type = v_item_type
    and not (d.dietary_flags && up.dietary_restrictions)
    and (
      up.planning_mode <> 'reserves'
      or not exists (
        select 1
        from dish_ingredients di
        join ingredients i on i.id = di.ingredient_id
        where di.dish_id = d.id
          and i.is_staple = false
          and not exists (
            select 1 from available_ingredients ai
            where ai.user_id = v_user_id
              and ai.week_start = v_week_start
              and ai.ingredient_id = di.ingredient_id
          )
      )
    )
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
  v_new_item_type text;
  v_new_flags text[];
  v_restrictions text[];
  v_result plan_items;
begin
  select pi.item_type, mp.user_id into v_item_type, v_user_id
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
  v_dish_item_type text;
  v_dish_flags text[];
  v_restrictions text[];
  v_result plan_items;
begin
  select user_id into v_user_id from meal_plans
  where id = target_plan_id and user_id = auth.uid();

  if v_user_id is null then
    raise exception 'meal plan not found or not owned by the current user';
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


-- MP-064: make-extra carry-over. The dish is already planned (and was already dietary-checked
-- when it was originally placed), so this deliberately does not re-run the dietary/eligibility
-- gate — it copies a known-safe dish_id forward, not a new choice. Deliberately bypasses in-week
-- and 10-day repeat handling by design (technical spec §4 item 3: "deliberately bypassing the
-- no-repeat rule. One boolean on the plan entry") — `make_extra = true` is what distinguishes this
-- from an accidental duplicate for every downstream reader (variety history, edit-time indicators).
create or replace function carry_over_plan_item(source_plan_item_id uuid, target_plan_id uuid)
returns plan_items
language plpgsql
security definer
set search_path = public
as $$
declare
  v_source_user_id uuid;
  v_target_user_id uuid;
  v_item_type text;
  v_dish_id uuid;
  v_result plan_items;
begin
  select mp.user_id, pi.item_type, pi.dish_id
    into v_source_user_id, v_item_type, v_dish_id
  from plan_items pi
  join meal_plans mp on mp.id = pi.plan_id
  where pi.id = source_plan_item_id and mp.user_id = auth.uid() and pi.status = 'filled';

  if v_source_user_id is null then
    raise exception 'source plan item not found, not owned by the current user, or not filled';
  end if;

  select user_id into v_target_user_id from meal_plans
  where id = target_plan_id and user_id = auth.uid();

  if v_target_user_id is null then
    raise exception 'target meal plan not found or not owned by the current user';
  end if;

  insert into plan_items (plan_id, item_type, dish_id, status, make_extra)
  values (target_plan_id, v_item_type, v_dish_id, 'filled', true)
  returning * into v_result;

  return v_result;
end;
$$;

revoke all on function carry_over_plan_item(uuid, uuid) from public;
grant execute on function carry_over_plan_item(uuid, uuid) to authenticated;
