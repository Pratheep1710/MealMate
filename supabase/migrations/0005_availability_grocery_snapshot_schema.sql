-- MP-011: Ingredient availability and grocery snapshot schema.
-- Source: version1_mealPlanner_technical.md §4. available_ingredients is populated only for
-- planning_mode = 'reserves' users (enforced at the app layer, not a DB constraint — see functional
-- spec §5). grocery_list_snapshot is the frozen "week ready" list both modes read from (functional
-- spec §6 / technical spec §6): the app layer, not this schema, decides suggestion-vs-reserves
-- content shape, since the jsonb payload is intentionally schema-flexible for that.

create table available_ingredients (
  user_id uuid not null references user_profiles(id) on delete cascade,
  week_start date not null,
  ingredient_id uuid not null references ingredients(id) on delete cascade,
  primary key (user_id, week_start, ingredient_id)
);

create table grocery_list_snapshot (
  user_id uuid not null references user_profiles(id) on delete cascade,
  week_start date not null,
  ingredients jsonb not null,  -- [{ingredient_id, name}, ...] at snapshot time
  created_at timestamptz not null default now(),
  primary key (user_id, week_start)
);
