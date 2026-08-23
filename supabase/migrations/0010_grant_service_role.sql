-- Self-discovered while verifying the PR #1 planning_mode fix against the live project (not a
-- reviewer comment): `service_role` had `rolbypassrls = true` (correct — Supabase sets this at
-- the platform level) but ZERO table-level grants on any table in this schema — only the
-- ownership-cascade TRIGGER/REFERENCES/TRUNCATE privileges, no SELECT/INSERT/UPDATE/DELETE.
-- BYPASSRLS skips row-level *policy* checks; it does not substitute for the table-level privilege
-- check PostgREST still performs first. Every scheduled job in the architecture (weekly
-- generation, daily notifications, catalog ingestion — technical spec §7 "Service-role key usage:
-- Scheduled batch jobs only") authenticates as service_role and would fail against this project
-- as it stood before this migration.

grant all privileges on all tables in schema public to service_role;
grant all privileges on all sequences in schema public to service_role;
grant all privileges on all functions in schema public to service_role;

-- Cover tables created by future migrations too, not just the ones that exist today.
alter default privileges in schema public grant all privileges on tables to service_role;
alter default privileges in schema public grant all privileges on sequences to service_role;
alter default privileges in schema public grant all privileges on functions to service_role;
