-- Phase 8 (MP-024/025/026): onboarding's 7-question set adds a diet-type axis
-- (Vegetarian/Eggetarian/Non-vegetarian, Q1), a meat-type preference (Q2), and an egg-frequency
-- preference (Q4) that `nonveg_days_per_week`/`dietary_restrictions` alone can't express:
--   - Eggetarian needs "no meat, but eggs OK" — impossible with the existing binary
--     `dishes.veg_or_nonveg` alone, since egg dishes are stored as `veg_or_nonveg = 'nonveg'`.
--   - `dishes.meat_type` (chicken/mutton/fish/seafood/other, added by 0016 *anticipating this exact
--     onboarding question*) has no profile-side column to compare against.
-- No change needed on `dishes`: the existing `dietary_flags @> array['Egg']` tag (already forced
-- onto every egg-diet dish by the ingestion pipeline, supabase/seed/catalog_taxonomy.py) is reused
-- as the "is this dish an egg dish" signal — see backend/app/services/generation_eligibility.py's
-- `_is_egg_dish`. `dishes.meat_type` already carries exactly Q2's vocabulary.

-- Default 'vegetarian' rather than 'nonvegetarian': it's the only value self-consistent with
-- every other new column's own default (egg_frequency defaults null, meat_types defaults '{}',
-- and nonveg_days_per_week/nonveg_day_pattern have no default at all, i.e. null) — a bare insert
-- that omits every Phase 8 column entirely (any pre-existing test/tooling insert not updated for
-- this migration) must not trip the coupling constraints below just by using the column defaults.
alter table user_profiles add column diet_type text not null default 'vegetarian';

-- Backfill before constraining: pre-existing rows (pre-dating this column) have no recorded
-- diet_type. Best-effort derive from the existing meat-quota field — "eggetarian" can't be
-- recovered from history since nothing distinguished it before this migration. Live project data
-- as of this migration is all fresh test/seed rows (no real onboarding traffic yet, MP-024 wasn't
-- built until this phase), so this is a documented limitation for future environments, not a
-- correction of real user data.
update user_profiles set diet_type = case
  when coalesce(nonveg_days_per_week, 0) = 0 then 'vegetarian'
  else 'nonvegetarian'
end;

alter table user_profiles add constraint user_profiles_diet_type_valid
  check (diet_type in ('vegetarian', 'eggetarian', 'nonvegetarian'));

-- Q2: which meats (only meaningful for Non-vegetarian). Empty means "no restriction, any meat
-- type" — matches how an empty dietary_restrictions means no restriction, same convention.
alter table user_profiles add column meat_types text[] not null default '{}';

alter table user_profiles add constraint user_profiles_meat_types_valid
  check (meat_types <@ array['chicken', 'mutton', 'fish', 'seafood', 'other']::text[]);

alter table user_profiles add constraint user_profiles_meat_types_requires_nonvegetarian
  check (diet_type = 'nonvegetarian' or meat_types = '{}');

-- Q4: how often eggs are permitted. Null only for Vegetarian (Q4 is never shown to that branch);
-- required (not null) for Eggetarian/Non-vegetarian, per the brief's exact branching.
alter table user_profiles add column egg_frequency text;

alter table user_profiles add constraint user_profiles_egg_frequency_valid
  check (egg_frequency is null or egg_frequency in ('any', 'nonveg_days', 'specific', 'never'));

alter table user_profiles add constraint user_profiles_egg_frequency_matches_diet_type
  check (
    (diet_type = 'vegetarian' and egg_frequency is null)
    or (diet_type <> 'vegetarian' and egg_frequency is not null)
  );

-- Only populated when egg_frequency = 'specific'; empty otherwise (mirrors nonveg_day_pattern's
-- own shape/convention, abbreviated-or-full day names normalized the same way client-side).
alter table user_profiles add column egg_day_pattern text[] not null default '{}';

alter table user_profiles add constraint user_profiles_egg_day_pattern_requires_specific
  check (egg_frequency = 'specific' or egg_day_pattern = '{}');

-- Q5 "Other": free text for manual triage only, per the brief's explicit instruction — never an
-- enforced exclusion, never reaches a generation or swap-time LLM call. Enforced by omission: no
-- repository or service module reads this column into a prompt payload anywhere in this codebase.
alter table user_profiles add column allergy_other_text text;

-- The existing meat-quota fields (nonveg_days_per_week/nonveg_day_pattern) are meaningless without
-- a meat quota — force them inert at the DB layer for diet_types that never have one, belt-and-
-- suspenders alongside the mirrored Pydantic model_validator (app/models/profile.py).
alter table user_profiles add constraint user_profiles_nonveg_days_requires_nonvegetarian
  check (diet_type = 'nonvegetarian' or coalesce(nonveg_days_per_week, 0) = 0);

alter table user_profiles add constraint user_profiles_nonveg_pattern_requires_nonvegetarian
  check (
    diet_type = 'nonvegetarian' or nonveg_day_pattern is null or nonveg_day_pattern = '{}'
  );

-- New onboarding-writable columns join the existing mutable set (0009's grant list) — none of
-- these is the one deliberately-immutable field (that's still planning_mode alone, untouched here).
grant update (diet_type, meat_types, egg_frequency, egg_day_pattern, allergy_other_text)
  on user_profiles to authenticated;
