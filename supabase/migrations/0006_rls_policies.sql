-- MP-013: Row Level Security policies.
-- Depends on 0002-0005 (MP-008,009,010,011) and Supabase Auth (MP-012) being in place.
-- Least-privilege: catalog tables are readable by any authenticated user and writable only by the
-- service_role (used exclusively by scheduled backend jobs, per technical spec §2.3/§7). Every
-- user-owned table is scoped to auth.uid() = user_id (or, for plan_items, scoped via its parent
-- meal_plans row) — cross-user reads/writes must be denied, own-data access must succeed. See
-- supabase/tests/ for the negative multi-tenant tests this AC requires.

-- ---------------------------------------------------------------------------
-- Catalog tables: read-only to authenticated users, not user-scoped.
-- ---------------------------------------------------------------------------

alter table dishes enable row level security;
alter table ingredients enable row level security;
alter table ingredient_aliases enable row level security;
alter table dish_ingredients enable row level security;

grant select on dishes, ingredients, ingredient_aliases, dish_ingredients to authenticated;

create policy dishes_select_all on dishes
  for select to authenticated using (true);

create policy ingredients_select_all on ingredients
  for select to authenticated using (true);

create policy ingredient_aliases_select_all on ingredient_aliases
  for select to authenticated using (true);

create policy dish_ingredients_select_all on dish_ingredients
  for select to authenticated using (true);

-- No insert/update/delete policies for `authenticated` on catalog tables: only service_role
-- (which bypasses RLS entirely) can write, via the MP-018 ingestion job.

-- ---------------------------------------------------------------------------
-- user_profiles — own row only.
-- ---------------------------------------------------------------------------

alter table user_profiles enable row level security;
grant select, insert, update on user_profiles to authenticated;

create policy user_profiles_select_own on user_profiles
  for select to authenticated using (id = auth.uid());

create policy user_profiles_insert_own on user_profiles
  for insert to authenticated with check (id = auth.uid());

create policy user_profiles_update_own on user_profiles
  for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

-- ---------------------------------------------------------------------------
-- user_favorite_dishes — own rows only.
-- ---------------------------------------------------------------------------

alter table user_favorite_dishes enable row level security;
grant select, insert, delete on user_favorite_dishes to authenticated;

create policy user_favorite_dishes_select_own on user_favorite_dishes
  for select to authenticated using (user_id = auth.uid());

create policy user_favorite_dishes_insert_own on user_favorite_dishes
  for insert to authenticated with check (user_id = auth.uid());

create policy user_favorite_dishes_delete_own on user_favorite_dishes
  for delete to authenticated using (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- meal_plans — read-only to the owning user; rows are written by the generation job
-- (service_role) only, never directly by the client.
-- ---------------------------------------------------------------------------

alter table meal_plans enable row level security;
grant select on meal_plans to authenticated;

create policy meal_plans_select_own on meal_plans
  for select to authenticated using (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- plan_items — scoped via the owning meal_plans row. Full CRUD for the owner: this is the
-- item-level edit path (swap/add/remove, functional spec §6) and the quick-swap RPC target.
-- ---------------------------------------------------------------------------

alter table plan_items enable row level security;
grant select, insert, update, delete on plan_items to authenticated;

create policy plan_items_select_own on plan_items
  for select to authenticated using (
    exists (
      select 1 from meal_plans
      where meal_plans.id = plan_items.plan_id
        and meal_plans.user_id = auth.uid()
    )
  );

create policy plan_items_insert_own on plan_items
  for insert to authenticated with check (
    exists (
      select 1 from meal_plans
      where meal_plans.id = plan_items.plan_id
        and meal_plans.user_id = auth.uid()
    )
  );

create policy plan_items_update_own on plan_items
  for update to authenticated using (
    exists (
      select 1 from meal_plans
      where meal_plans.id = plan_items.plan_id
        and meal_plans.user_id = auth.uid()
    )
  ) with check (
    exists (
      select 1 from meal_plans
      where meal_plans.id = plan_items.plan_id
        and meal_plans.user_id = auth.uid()
    )
  );

create policy plan_items_delete_own on plan_items
  for delete to authenticated using (
    exists (
      select 1 from meal_plans
      where meal_plans.id = plan_items.plan_id
        and meal_plans.user_id = auth.uid()
    )
  );

-- ---------------------------------------------------------------------------
-- generation_jobs — read-only to the owning user; written only by scheduled jobs (service_role).
-- ---------------------------------------------------------------------------

alter table generation_jobs enable row level security;
grant select on generation_jobs to authenticated;

create policy generation_jobs_select_own on generation_jobs
  for select to authenticated using (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- notification_log — read-only to the owning user; written only by scheduled jobs (service_role).
-- ---------------------------------------------------------------------------

alter table notification_log enable row level security;
grant select on notification_log to authenticated;

create policy notification_log_select_own on notification_log
  for select to authenticated using (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- available_ingredients — full CRUD for the owning user (v1 manual checklist, direct Supabase
-- write per technical spec §2.3/§3).
-- ---------------------------------------------------------------------------

alter table available_ingredients enable row level security;
grant select, insert, update, delete on available_ingredients to authenticated;

create policy available_ingredients_select_own on available_ingredients
  for select to authenticated using (user_id = auth.uid());

create policy available_ingredients_insert_own on available_ingredients
  for insert to authenticated with check (user_id = auth.uid());

create policy available_ingredients_update_own on available_ingredients
  for update to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

create policy available_ingredients_delete_own on available_ingredients
  for delete to authenticated using (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- grocery_list_snapshot — read-only to the owning user; frozen at "week ready" time by the
-- generation job (service_role), never written by the client (technical spec §6).
-- ---------------------------------------------------------------------------

alter table grocery_list_snapshot enable row level security;
grant select on grocery_list_snapshot to authenticated;

create policy grocery_list_snapshot_select_own on grocery_list_snapshot
  for select to authenticated using (user_id = auth.uid());
