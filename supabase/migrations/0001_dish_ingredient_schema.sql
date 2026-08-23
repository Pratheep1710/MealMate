-- MP-007: Core dish and ingredient schema.
-- Source: version1_mealPlanner_technical.md §4. Catalog tables — read-only at the app layer,
-- not user-scoped (see 0006_rls_policies.sql / MP-013).
--
-- gen_random_uuid() is used below as a core PostgreSQL 13+ function (pg_catalog), not the
-- pgcrypto extension's version — Supabase's own template also predefines it this way, so no
-- `create extension pgcrypto` is needed here.

create table dishes (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  item_type text not null,        -- tiffin | rice | gravy | poriyal | kootu | curd | snack | sweet
  veg_or_nonveg text not null,    -- veg | nonveg
  region_style text,
  prep_minutes int,
  track_variety boolean not null default true,  -- false for rice, curd — exempt from 10-day rule
  dietary_flags text[] not null default '{}'    -- e.g. {dairy, gluten, nuts} — enforced downstream
);

create table ingredients (
  id uuid primary key default gen_random_uuid(),
  canonical_name text not null unique,
  is_staple boolean not null default false  -- true = excluded from grocery-photo matching
);

create table ingredient_aliases (
  alias_text text primary key,
  ingredient_id uuid not null references ingredients(id) on delete cascade
);

create table dish_ingredients (
  dish_id uuid not null references dishes(id) on delete cascade,
  ingredient_id uuid not null references ingredients(id) on delete cascade,
  primary key (dish_id, ingredient_id)
);

create index dish_ingredients_ingredient_id_idx on dish_ingredients (ingredient_id);
create index dishes_item_type_idx on dishes (item_type);
