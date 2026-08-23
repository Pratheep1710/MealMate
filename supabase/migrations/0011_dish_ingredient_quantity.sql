-- Review fix (PR #1) — see docs/MP-007a-grocery-quantity-decision.md for the full decision
-- record. Functional spec §4 item 1 promises a "quantity-aggregated" weekly grocery list, but
-- dish_ingredients only recorded presence (no amount, no unit) — nothing to aggregate. Adds a
-- nullable quantity + unit per (dish, ingredient), representing the amount needed for one
-- standard serving of that dish. Nullable, not required: some ingredients (salt, spices used "to
-- taste") never have a fixed quantity in real recipes, so presence-only must remain a valid state
-- permanently, not just during a migration-safety window before catalog data exists.

alter table dish_ingredients
  add column quantity numeric,
  add column unit text;

alter table dish_ingredients
  add constraint dish_ingredients_quantity_unit_together check (
    (quantity is null and unit is null) or (quantity is not null and unit is not null)
  );
