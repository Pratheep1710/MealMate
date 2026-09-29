-- Phase 9 (MP-092): WeekPlanScreen's progressive-first-plan-reveal state learns that MP-094's
-- generation finished the same way MP-069's "your week is ready" push already does — a
-- generation_jobs row for this user flipping to status = 'done' — via a Supabase Realtime
-- postgres_changes subscription, not a new polling loop. postgres_changes only fires for tables
-- explicitly added to the `supabase_realtime` publication; generation_jobs's existing RLS select
-- policy (0006_rls_policies.sql's generation_jobs_select_own) is what Realtime then uses to scope
-- delivered change events to the owning user, the same way it already scopes a direct select.
--
-- The publication-existence guard (rather than a bare `create publication supabase_realtime`) is
-- for portability: a real Supabase project already has this publication from its own platform
-- bootstrap (creating it again would error), but backend/tests/conftest.py's throwaway Postgres
-- and supabase/tests' pglite instance build the schema from just these migration files against a
-- vanilla Postgres with no such bootstrap.
do $$
begin
  if not exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    create publication supabase_realtime;
  end if;
end $$;

alter publication supabase_realtime add table generation_jobs;
