-- PR #12 review finding [P1]: dishes.dietary_flags now has a DB-enforced controlled vocabulary
-- (0016), but user_profiles.dietary_restrictions was left unconstrained — existing tests and any
-- real onboarding data could carry lowercase values like "dairy"/"nuts". The hard-exclusion check
-- (backend/app/repositories/catalog.py's get_candidates, `dietary_flags && exclude_dietary_flags`)
-- is a Postgres array-overlap test, which is case-sensitive: a profile carrying "dairy" would never
-- overlap a dish tagged "Milk-Dairy", silently defeating the exclusion this column exists for.
--
-- Backfill first, constraint second — normalizes any pre-existing lowercase/singular variants to
-- the real vocabulary before the CHECK constraint would reject them outright. Live project data
-- as of this migration is all empty arrays (no onboarding UI writes this yet — MP-024 isn't built),
-- so this is a no-op there, but the mapping is real, not decorative, for any environment that does
-- have data by the time this runs.
update user_profiles
set dietary_restrictions = (
  select coalesce(array_agg(distinct normalized.value), '{}')
  from (
    select case lower(elem)
      when 'nuts' then 'Nuts'
      when 'nut' then 'Nuts'
      when 'peanut' then 'Nuts'
      when 'peanuts' then 'Nuts'
      when 'milk-dairy' then 'Milk-Dairy'
      when 'dairy' then 'Milk-Dairy'
      when 'milk' then 'Milk-Dairy'
      when 'gluten' then 'Gluten'
      when 'egg' then 'Egg'
      when 'eggs' then 'Egg'
      when 'seafood' then 'Seafood'
      when 'fish' then 'Seafood'
      when 'sesame' then 'Sesame'
      else elem  -- left as-is; the constraint below will reject anything that's still unrecognized
    end as value
    from unnest(dietary_restrictions) as elem
  ) as normalized
)
where dietary_restrictions is not null and dietary_restrictions <> '{}';

-- Same controlled vocabulary as dishes_dietary_flags_valid (0016), same reasoning: MP-017's
-- decided list (Phase 5 brief §0), matching the onboarding allergy question's own values exactly.
alter table user_profiles add constraint user_profiles_dietary_restrictions_valid
  check (dietary_restrictions <@ array['Nuts', 'Milk-Dairy', 'Gluten', 'Egg', 'Seafood', 'Sesame']::text[]);
