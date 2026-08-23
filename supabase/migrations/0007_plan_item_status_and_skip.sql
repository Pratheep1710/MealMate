-- Review fix (PR #1): two gaps between the frozen v1 scope and the schema.
--
-- 1. Technical spec §5.1 step 5 requires a fallback output state: when a (day, slot, item_type)
--    has zero eligible candidates even after relaxing the 10-day rule, the app must mark that item
--    `needs_manual_pick` and surface it for manual choice — never leave it blank, never invent a
--    sentinel dish. `plan_items.dish_id` was `not null`, so that state had nowhere to live.
-- 2. Functional spec §6 requires a per-slot skip/eating-out toggle that drops the slot from the
--    grocery list and excludes it from variety/history tracking. `meal_plans` had no such flag.

alter table plan_items
  alter column dish_id drop not null,
  add column status text not null default 'filled';

alter table plan_items
  add constraint plan_items_status_check check (status in ('filled', 'needs_manual_pick')),
  add constraint plan_items_dish_id_required_unless_manual_pick check (
    status = 'needs_manual_pick' or dish_id is not null
  );

alter table meal_plans
  add column is_skipped boolean not null default false;
