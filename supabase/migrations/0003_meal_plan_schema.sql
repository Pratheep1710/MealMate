-- MP-009: Meal plan schema.
-- Source: version1_mealPlanner_technical.md §4. Six daily slots enforced via check constraint;
-- unique (user_id, plan_date, slot) is the idempotency guarantee for generation writes.

create table meal_plans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references user_profiles(id) on delete cascade,
  plan_date date not null,
  slot text not null,              -- morning | afternoon | night | snack_1 | snack_2 | snack_3
  created_at timestamptz not null default now(),
  constraint meal_plans_slot_check check (
    slot in ('morning', 'afternoon', 'night', 'snack_1', 'snack_2', 'snack_3')
  ),
  unique (user_id, plan_date, slot)
);

create table plan_items (
  id uuid primary key default gen_random_uuid(),
  plan_id uuid not null references meal_plans(id) on delete cascade,
  item_type text not null,
  dish_id uuid not null references dishes(id),
  make_extra boolean not null default false  -- batch-cook / intentional repeat flag
);

create index plan_items_plan_id_idx on plan_items (plan_id);
create index meal_plans_user_id_plan_date_idx on meal_plans (user_id, plan_date);
