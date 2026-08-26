-- DEV-ONLY SEED SCRIPT — not a migration, not the MP-018 catalog ingestion pipeline.
--
-- Phase 4 brief (meal-planner-phase4-claude-code-brief.md §0/§1): the real dish catalog (~200
-- dishes, MP-003) and full taxonomy mapping (MP-015) are still blocked on the dish workbook.
-- This inserts a small, real set of Tamil Nadu dishes — enough variety to fill six slots across a
-- week without visible repetition — plus one real week of `meal_plans`/`plan_items` for the
-- existing MP-023 test user, so the already-built read paths (MP-027's WeekPlanScreen) have true
-- Supabase rows to render instead of UI placeholders.
--
-- Explicitly out of scope here (do not backfill): `dietary_flags` (MP-017 not resolved — left at
-- the schema default `{}`), full ingredient taxonomy/alias mapping (MP-015). Only minimal valid
-- values for required fields are set.
--
-- Safe to re-run: dishes/ingredients are inserted only if a same-named row doesn't already exist
-- (no unique constraint on `dishes.name` to hang `on conflict` off), and the meal_plans/plan_items
-- block re-derives `plan_date` from `current_date` each run, so re-running later still populates
-- "today onward" rather than leaving a stale past week.
--
-- Run via: python supabase/seed/run_seed.py  (reads SUPABASE_DB_* env vars, same as
-- supabase/apply_migrations.py). Never counted toward MP-020's catalog coverage validation.

begin;

-- ---------------------------------------------------------------------------
-- Ingredients — a shared pool covering the dishes below, not a full taxonomy.
-- ---------------------------------------------------------------------------

insert into ingredients (canonical_name, is_staple)
select v.canonical_name, v.is_staple
from (values
  ('rice', true),
  ('toor dal', true),
  ('moong dal', true),
  ('urad dal', true),
  ('chana dal', true),
  ('tamarind', true),
  ('mustard seeds', true),
  ('curry leaves', true),
  ('turmeric', true),
  ('chili powder', true),
  ('salt', true),
  ('oil', true),
  ('ghee', true),
  ('asafoetida', true),
  ('cardamom', true),
  ('jaggery', true),
  ('onion', false),
  ('tomato', false),
  ('garlic', false),
  ('coconut', false),
  ('semiya', false),
  ('milk', false),
  ('chicken', false),
  ('fish', false),
  ('cabbage', false),
  ('carrot', false),
  ('beans', false),
  ('curd', false),
  ('lemon', false),
  ('peanuts', false)
) as v(canonical_name, is_staple)
on conflict (canonical_name) do nothing;

-- ---------------------------------------------------------------------------
-- Dishes — 20 real Tamil Nadu dishes spanning every item_type.
-- track_variety = false for the everyday staples (plain rice, curd rice, murukku, payasam) that a
-- real household repeats often, per 0001's own "false for rice, curd — exempt from 10-day rule"
-- comment, extended here to the other clearly-repeatable staples.
-- ---------------------------------------------------------------------------

insert into dishes (name, item_type, veg_or_nonveg, region_style, prep_minutes, track_variety)
select v.name, v.item_type, v.veg_or_nonveg, v.region_style, v.prep_minutes, v.track_variety
from (values
  ('Idli',               'tiffin',  'veg',    'Tamil Nadu', 30, true),
  ('Plain Dosa',         'tiffin',  'veg',    'Tamil Nadu', 25, true),
  ('Ven Pongal',         'tiffin',  'veg',    'Tamil Nadu', 25, true),
  ('Uttapam',            'tiffin',  'veg',    'Tamil Nadu', 25, true),
  ('Steamed Rice',       'rice',    'veg',    'Tamil Nadu', 25, false),
  ('Lemon Rice',         'rice',    'veg',    'Tamil Nadu', 20, true),
  ('Tomato Rice',        'rice',    'veg',    'Tamil Nadu', 25, true),
  ('Curd Rice',          'curd',    'veg',    'Tamil Nadu', 10, false),
  ('Sambar',             'gravy',   'veg',    'Tamil Nadu', 35, true),
  ('Kara Kuzhambu',      'gravy',   'veg',    'Tamil Nadu', 35, true),
  ('Rasam',              'gravy',   'veg',    'Tamil Nadu', 20, true),
  ('Chicken Chettinad',  'gravy',   'nonveg', 'Chettinad',  45, true),
  ('Meen Kuzhambu',      'gravy',   'nonveg', 'Tamil Nadu', 40, true),
  ('Beans Poriyal',      'poriyal', 'veg',    'Tamil Nadu', 20, true),
  ('Cabbage Poriyal',    'poriyal', 'veg',    'Tamil Nadu', 20, true),
  ('Carrot Poriyal',     'poriyal', 'veg',    'Tamil Nadu', 20, true),
  ('Mixed Veg Kootu',    'kootu',   'veg',    'Tamil Nadu', 30, true),
  ('Paruppu Kootu',      'kootu',   'veg',    'Tamil Nadu', 25, true),
  ('Murukku',            'snack',   'veg',    'Tamil Nadu', 45, false),
  ('Semiya Payasam',     'sweet',   'veg',    'Tamil Nadu', 20, false)
) as v(name, item_type, veg_or_nonveg, region_style, prep_minutes, track_variety)
where not exists (select 1 from dishes d where d.name = v.name);

-- ---------------------------------------------------------------------------
-- dish_ingredients — links each dish to 2-4 ingredients from the pool above.
-- ---------------------------------------------------------------------------

insert into dish_ingredients (dish_id, ingredient_id)
select d.id, i.id
from (values
  ('Idli', 'rice'), ('Idli', 'urad dal'),
  ('Plain Dosa', 'rice'), ('Plain Dosa', 'urad dal'),
  ('Ven Pongal', 'rice'), ('Ven Pongal', 'moong dal'), ('Ven Pongal', 'ghee'),
  ('Uttapam', 'rice'), ('Uttapam', 'urad dal'), ('Uttapam', 'onion'),
  ('Steamed Rice', 'rice'),
  ('Lemon Rice', 'rice'), ('Lemon Rice', 'lemon'), ('Lemon Rice', 'mustard seeds'), ('Lemon Rice', 'peanuts'),
  ('Tomato Rice', 'rice'), ('Tomato Rice', 'tomato'), ('Tomato Rice', 'onion'),
  ('Curd Rice', 'rice'), ('Curd Rice', 'curd'),
  ('Sambar', 'toor dal'), ('Sambar', 'tamarind'), ('Sambar', 'onion'), ('Sambar', 'tomato'),
  ('Kara Kuzhambu', 'tamarind'), ('Kara Kuzhambu', 'onion'), ('Kara Kuzhambu', 'chili powder'),
  ('Rasam', 'tamarind'), ('Rasam', 'tomato'), ('Rasam', 'garlic'),
  ('Chicken Chettinad', 'chicken'), ('Chicken Chettinad', 'onion'), ('Chicken Chettinad', 'coconut'),
  ('Meen Kuzhambu', 'fish'), ('Meen Kuzhambu', 'tamarind'), ('Meen Kuzhambu', 'onion'),
  ('Beans Poriyal', 'beans'), ('Beans Poriyal', 'coconut'), ('Beans Poriyal', 'mustard seeds'),
  ('Cabbage Poriyal', 'cabbage'), ('Cabbage Poriyal', 'coconut'), ('Cabbage Poriyal', 'mustard seeds'),
  ('Carrot Poriyal', 'carrot'), ('Carrot Poriyal', 'coconut'), ('Carrot Poriyal', 'mustard seeds'),
  ('Mixed Veg Kootu', 'carrot'), ('Mixed Veg Kootu', 'beans'), ('Mixed Veg Kootu', 'cabbage'), ('Mixed Veg Kootu', 'moong dal'),
  ('Paruppu Kootu', 'moong dal'), ('Paruppu Kootu', 'coconut'),
  ('Murukku', 'rice'), ('Murukku', 'urad dal'), ('Murukku', 'chana dal'),
  ('Semiya Payasam', 'semiya'), ('Semiya Payasam', 'milk'), ('Semiya Payasam', 'jaggery'), ('Semiya Payasam', 'cardamom')
) as v(dish_name, ingredient_name)
join dishes d on d.name = v.dish_name
join ingredients i on i.canonical_name = v.ingredient_name
on conflict (dish_id, ingredient_id) do nothing;

-- ---------------------------------------------------------------------------
-- One real week of meal_plans + plan_items for the MP-023 test user
-- (ci-test-user@mealmate.test — reused, not a new user). plan_date is always current_date-relative
-- so re-running this seed later still populates "today onward" for demoing MP-027.
-- ---------------------------------------------------------------------------

do $$
declare
  test_user_id uuid;
  v_plan_id uuid;
  row_data record;
begin
  select id into test_user_id from auth.users where email = 'ci-test-user@mealmate.test';

  if test_user_id is null then
    raise notice 'Skipping meal_plans/plan_items seed: ci-test-user@mealmate.test not found. '
      'Run backend/scripts/provision_ci_test_users.py first (see docs/MP-023-cross-user-rls-test.md).';
    return;
  end if;

  -- Ensure a user_profiles row exists (meal_plans.user_id FKs to it, not directly to auth.users).
  insert into user_profiles (id, dietary_restrictions, grocery_day)
  values (test_user_id, '{}', 'monday')
  on conflict (id) do nothing;

  for row_data in
    select * from (values
      -- MP-061 review fix: all six slots (morning, snack_1, afternoon, snack_2, night, snack_3 —
      -- WeekPlanScreen's CHRONOLOGICAL_SLOTS order) populated every day, not just four, so MP-027
      -- is verified against a representative full day rather than one with gaps.
      (0, 'morning',   'tiffin',  'Idli'),
      (0, 'morning',   'gravy',   'Sambar'),
      (0, 'snack_1',   'snack',   'Murukku'),
      (0, 'afternoon', 'rice',    'Steamed Rice'),
      (0, 'afternoon', 'gravy',   'Kara Kuzhambu'),
      (0, 'afternoon', 'poriyal', 'Beans Poriyal'),
      (0, 'snack_2',   'sweet',   'Semiya Payasam'),
      (0, 'night',     'curd',    'Curd Rice'),
      (0, 'snack_3',   'snack',   'Murukku'),

      (1, 'morning',   'tiffin',  'Plain Dosa'),
      (1, 'morning',   'gravy',   'Rasam'),
      (1, 'snack_1',   'snack',   'Murukku'),
      (1, 'afternoon', 'rice',    'Steamed Rice'),
      (1, 'afternoon', 'gravy',   'Chicken Chettinad'),
      (1, 'afternoon', 'poriyal', 'Cabbage Poriyal'),
      (1, 'snack_2',   'sweet',   'Semiya Payasam'),
      (1, 'night',     'rice',    'Lemon Rice'),
      (1, 'snack_3',   'snack',   'Murukku'),

      (2, 'morning',   'tiffin',  'Ven Pongal'),
      (2, 'morning',   'gravy',   'Sambar'),
      (2, 'snack_1',   'snack',   'Murukku'),
      (2, 'afternoon', 'rice',    'Steamed Rice'),
      (2, 'afternoon', 'kootu',   'Mixed Veg Kootu'),
      (2, 'afternoon', 'poriyal', 'Carrot Poriyal'),
      (2, 'snack_2',   'sweet',   'Semiya Payasam'),
      (2, 'night',     'tiffin',  'Uttapam'),
      (2, 'snack_3',   'snack',   'Murukku'),

      (3, 'morning',   'rice',    'Tomato Rice'),
      (3, 'snack_1',   'snack',   'Murukku'),
      (3, 'afternoon', 'rice',    'Steamed Rice'),
      (3, 'afternoon', 'gravy',   'Meen Kuzhambu'),
      (3, 'afternoon', 'poriyal', 'Beans Poriyal'),
      (3, 'snack_2',   'snack',   'Murukku'),
      (3, 'night',     'curd',    'Curd Rice'),
      (3, 'snack_3',   'sweet',   'Semiya Payasam'),

      (4, 'morning',   'tiffin',  'Idli'),
      (4, 'morning',   'gravy',   'Rasam'),
      (4, 'snack_1',   'snack',   'Murukku'),
      (4, 'afternoon', 'rice',    'Steamed Rice'),
      (4, 'afternoon', 'gravy',   'Kara Kuzhambu'),
      (4, 'afternoon', 'kootu',   'Paruppu Kootu'),
      (4, 'snack_2',   'sweet',   'Semiya Payasam'),
      (4, 'night',     'tiffin',  'Plain Dosa'),
      (4, 'snack_3',   'snack',   'Murukku'),

      (5, 'morning',   'tiffin',  'Ven Pongal'),
      (5, 'morning',   'gravy',   'Sambar'),
      (5, 'snack_1',   'snack',   'Murukku'),
      (5, 'afternoon', 'rice',    'Lemon Rice'),
      (5, 'afternoon', 'poriyal', 'Cabbage Poriyal'),
      (5, 'snack_2',   'sweet',   'Semiya Payasam'),
      (5, 'night',     'curd',    'Curd Rice'),
      (5, 'snack_3',   'snack',   'Murukku'),

      (6, 'morning',   'tiffin',  'Uttapam'),
      (6, 'morning',   'gravy',   'Rasam'),
      (6, 'snack_1',   'snack',   'Murukku'),
      (6, 'afternoon', 'rice',    'Steamed Rice'),
      (6, 'afternoon', 'gravy',   'Chicken Chettinad'),
      (6, 'afternoon', 'poriyal', 'Carrot Poriyal'),
      (6, 'snack_2',   'sweet',   'Semiya Payasam'),
      (6, 'night',     'rice',    'Tomato Rice'),
      (6, 'snack_3',   'snack',   'Murukku')
    ) as t(day_offset, slot, item_type, dish_name)
    order by day_offset, slot
  loop
    insert into meal_plans (user_id, plan_date, slot)
    values (test_user_id, current_date + row_data.day_offset, row_data.slot)
    on conflict (user_id, plan_date, slot) do update set slot = excluded.slot
    returning id into v_plan_id;

    insert into plan_items (plan_id, item_type, dish_id)
    select v_plan_id, row_data.item_type, d.id
    from dishes d
    where d.name = row_data.dish_name
      and not exists (
        select 1 from plan_items pi
        where pi.plan_id = v_plan_id and pi.item_type = row_data.item_type
      );
  end loop;
end $$;

commit;
