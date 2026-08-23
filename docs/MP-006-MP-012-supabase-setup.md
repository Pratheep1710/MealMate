# MP-006 / MP-012 — Supabase Project Setup (manual, owner-only step)

Creating a Supabase account/project isn't something that can be done on your behalf — this is the
one step in Phase 1 that needs you. Everything downstream (migrations, config, RLS, mobile app) is
already written and tested against a stand-in Postgres locally, ready to point at the real thing.

## 1. Create the project (MP-006)

1. Sign up / log in at supabase.com, create a new project (pick a region close to where the app's
   users will be — Mumbai/Singapore for Tamil Nadu users).
2. Once provisioned: **Project Settings → API** — copy:
   - Project URL → `SUPABASE_URL`
   - `anon` `public` key → `SUPABASE_ANON_KEY`
   - `service_role` key → `SUPABASE_SERVICE_ROLE_KEY` (**never** put this in the mobile app or
     commit it — backend/scheduled-job use only, per the auth boundary in the technical spec §3)
3. Copy `backend/.env.example` to `backend/.env` and fill in the three values above, plus
   `OPENAI_API_KEY` / `OPENAI_MODEL`. `backend/app/config.py` (MP-014) will fail fast with a clear
   message if anything required is missing or malformed — run
   `backend/.venv/Scripts/python -m pytest backend/tests/test_config.py` any time to check.
4. For the mobile app, set `EXPO_PUBLIC_SUPABASE_URL` and `EXPO_PUBLIC_SUPABASE_ANON_KEY` in your
   shell (or an `.env` consumed by `mobile/app.config.ts`) — anon key only, never the service role
   key, since these ship inside the client bundle.

## 2. Apply the schema migrations (MP-007–011, MP-013)

The SQL in `supabase/migrations/` is already validated against real Postgres semantics (constraints,
FKs, and RLS isolation) via the pglite test suite in `supabase/tests/` — see MP-007–011/MP-013
status below. Apply it to the real project with either:

**Option A — Supabase CLI** (recommended once you have it installed):
```bash
supabase link --project-ref <your-project-ref>
supabase db push
```

**Option B — SQL Editor** (no CLI needed): open each file in `supabase/migrations/` in numeric
order (`0001_...` through `0006_rls_policies.sql`) and run it in the Supabase dashboard's SQL
Editor, one at a time, in order — `0006` depends on every table from `0002`–`0005` existing first.

## 3. Enable Auth and provision a test user (MP-012)

1. **Authentication → Providers** — email/password is enabled by default; leave it on for v1
   (mobile onboarding, functional spec §2, doesn't specify a different provider).
2. **Authentication → Users → Add user** — create one confirmed test user (any email/password) for
   the sign-in test below.
3. Set these in `backend/.env` (or your shell) to turn on the real integration test:
   ```
   SUPABASE_TEST_USER_EMAIL=<the test user's email>
   SUPABASE_TEST_USER_PASSWORD=<the test user's password>
   ```
4. Run it:
   ```bash
   backend/.venv/Scripts/python -m pytest backend/tests/test_supabase_auth.py -v
   ```
   Without those four env vars set, this test SKIPS (not fails) — that's the expected state until
   you've done steps 1–3 above. Once it passes, MP-012's AC ("test user can sign in and obtain a
   scoped JWT") is satisfied for real, not just locally simulated.

## 4. Re-run the RLS negative tests against the real project (optional but recommended)

`supabase/tests/rls.test.mjs` already proves the RLS policies are correct against real Postgres
semantics (pglite). Nothing further is required for MP-013's AC. If you want extra confidence
against the actual hosted project once step 2 is done, the same 21 assertions can be adapted to run
over `@supabase/supabase-js` against the live URL — not built here since the pglite suite already
gives an equivalent, faster-running, CI-friendly guarantee without needing live credentials.

## Status (updated after the live project was provisioned)

| Task | Status |
|---|---|
| MP-006 (project) | **Done.** Project `kuctkvxegfaqemosmtcs` (region ap-southeast-2) is live and reachable. |
| MP-007–011 (schema) | **Done.** All 6 migration files applied to the live project via `supabase/apply_migrations.py` (through the session pooler — the direct `db.*.supabase.co` host is IPv6-only and unreachable from this network). All 12 tables confirmed present. |
| MP-013 (RLS) | **Done.** All 12 tables have RLS enabled with the expected policy counts, verified live. A REST probe with the anon/publishable key against `dishes` correctly returned `permission denied` (Postgres role `anon` has no grants — only `authenticated` does, per design) — that's the RLS working as intended, not a bug. |
| MP-014 (config) | **Done.** `backend/.env` has real `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENAI_API_KEY` filled in. `OPENAI_MODEL` is still blank — config correctly fails fast until you pick a model name. |
| MP-012 (auth) | Auth (GoTrue) confirmed live at `/auth/v1/health`. The sign-in test still skips until you create a confirmed test user and set `SUPABASE_TEST_USER_EMAIL`/`SUPABASE_TEST_USER_PASSWORD` in `backend/.env` — see section 3. |

`supabase/apply_migrations.py` is a one-time apply script, not a migration framework — it has no
applied-state tracking, so re-running it against this project will fail loudly on the first
`create table` (expected, not a bug). Keep that in mind if the schema needs to change later: write
a new numbered migration file rather than re-running the existing ones.
