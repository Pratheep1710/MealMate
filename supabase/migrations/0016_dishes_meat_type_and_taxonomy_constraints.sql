-- MP-015: schema check before mapping the master catalogue. Onboarding's meat-preference question
-- (Chicken / Mutton / Fish / Seafood / Other, per the Phase 5 brief) has no matching column on
-- `dishes` — 0001 only has the binary `veg_or_nonveg`, which can't tell a chicken dish from a
-- mutton one. Adding it here, as a migration, per the brief's explicit instruction not to work
-- around a missing column with a data-mapping hack.
--
-- Nullable: only meaningful for veg_or_nonveg = 'nonveg', and even some nonveg rows (Egg-diet
-- dishes, or genuinely ambiguous "mixed meat" catalogue entries) legitimately have no single
-- protein — see supabase/seed/catalog_taxonomy.py's infer_meat_type for what gets reported instead
-- of guessed.
alter table dishes add column meat_type text;

alter table dishes add constraint dishes_meat_type_valid
  check (meat_type is null or meat_type in ('chicken', 'mutton', 'fish', 'seafood', 'other'));

-- A veg dish can't have a protein type.
alter table dishes add constraint dishes_meat_type_requires_nonveg
  check (meat_type is null or veg_or_nonveg = 'nonveg');

-- MP-017: dietary_flags controlled vocabulary, decided (Phase 5 brief §0) as exactly Nuts,
-- Milk-Dairy, Gluten, Egg, Seafood, Sesame — matching the app's onboarding allergy question
-- verbatim, including casing, so the same string values work on both sides of the hard-exclusion
-- array-overlap check (backend/app/repositories/catalog.py's get_candidates) without a UI-label to
-- DB-value translation layer. Supersedes the broader draft list in
-- docs/MP-017-dietary-flag-taxonomy.md (dairy/gluten/nuts/peanut/sesame/egg/soy/vegan/jain) — no
-- vegan/jain (onboarding doesn't collect them), peanut folded into Nuts (no separate flag in the
-- decided list; see catalog_taxonomy.py's tagging notes on why peanut still trips Nuts), soy
-- dropped.
alter table dishes add constraint dishes_dietary_flags_valid
  check (dietary_flags <@ array['Nuts', 'Milk-Dairy', 'Gluten', 'Egg', 'Seafood', 'Sesame']::text[]);

-- MP-018: the re-runnable ingestion pipeline (supabase/seed/ingest_catalog.py) upserts by name —
-- `load_master_catalogue.py`'s one-time bulk load only ever checked for existing names in
-- application code (see its own comment on why: no unique constraint to hang ON CONFLICT off).
-- This gives it one, so a second run updates in place instead of relying on a pre-query race-prone
-- existence check. Confirmed safe against live data first: all 573 current rows have distinct
-- lower(name).
create unique index dishes_name_lower_unique_idx on dishes (lower(name));
