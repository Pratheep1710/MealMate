# MP-007a — Grocery Quantity Model: Decision Record

Not one of the tracker's original four open items — surfaced during PR #1 review as a genuine
conflict between the functional spec and the frozen MP-007 schema, following the same brief
instruction the other four decisions did: surface it and get an explicit call rather than resolve
it silently. Numbered "007a" because it's a direct amendment to MP-007's schema, not a new
tracker task.

**Decision: add nullable `quantity` + `unit` to `dish_ingredients` (migration `0011`). Aggregate
by quantity when known; fall back to a presence-only bullet when not.**

## The conflict
- Functional spec §4 item 1: "Weekly grocery list — auto-generated, de-duplicated, ingredient
  **quantities aggregated** across the week's plan." Listed as the single top-priority feature.
- The frozen MP-007 schema (`dish_ingredients`, technical spec §4) recorded only
  `(dish_id, ingredient_id)` — presence, not amount. There was nothing to aggregate; the two
  documents were making incompatible promises about the same feature.

## Why nullable, not required
Real recipes have ingredients with no fixed quantity — salt, curry leaves, tempering spices used
"to taste." Forcing every `dish_ingredients` row to carry a quantity would mean inventing false
precision for those, or blocking catalog curation (MP-015–016) on a problem this schema doesn't
need to solve. Nullable quantity/unit is the permanent correct shape, not a temporary
migration-safety compromise: known amounts aggregate into real quantities ("Toor dal: 350g" summed
across the week's dishes), unknown ones still list the ingredient by name with no fabricated
number attached.

## What this means for downstream tasks
- `MP-015` (taxonomy mapping) and `MP-016` (canonical ingredients) should populate `quantity`/
  `unit` wherever the source data supports it, leaving both null otherwise — no requirement to
  backfill a number that isn't real.
- Grocery list generation (whichever task builds `grocery_list_snapshot`'s content, downstream of
  M4) groups by `(ingredient_id, unit)` and sums `quantity` for rows where it's set; ingredients
  with any null-quantity dish in the week's plan render as a plain checklist bullet alongside the
  aggregated ones — the list is always a mix of both, not one or the other.
- No change to `grocery_list_snapshot`'s `jsonb` shape at the schema level — it stays
  intentionally flexible; this decision only fixes what `dish_ingredients` can express in the
  first place.

## Revisit trigger
If catalog curation (MP-015–016) finds that most dishes genuinely have fixed, meaningful
quantities and the null case turns out rare — consider whether `unit` should be a constrained
enum instead of free text, once real values exist to enumerate from.
