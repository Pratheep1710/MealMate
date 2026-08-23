# MP-023 — Cross-User RLS Denial Test Setup (manual, owner-only step)

`mobile/src/lib/__tests__/rls-cross-user.test.ts` proves MP-013's RLS policies hold from the
actual mobile client path (supabase-js + a real signed-in JWT), not just from the backend's
pglite-based suite (`supabase/tests/rls.test.mjs`) or a service-role connection. Like
`backend/tests/test_supabase_auth.py` (MP-012), it **skips** rather than fails locally until a
live project and test users exist — but as of this fix, **CI now fails outright** (not skips) on
same-repo runs if the six env vars below aren't set as repo secrets, per review feedback on PR #5:
a silently-skipping "required" test is indistinguishable from one that was never wired up at all.
This doc is what turns it into a real, CI-enforced assertion.

## 1. Provision the two test users

Run the provisioning script once — it replaces the undocumented one-off Admin API call MP-012's
original test user was created with:

```bash
cd backend
SUPABASE_URL=<project URL> SUPABASE_SERVICE_ROLE_KEY=<service_role key> \
  .venv/bin/python scripts/provision_ci_test_users.py
```

It's idempotent: creates (or finds) `ci-test-user@mealmate.test` ("user A", MP-012's existing
user) and `ci-test-user-b@mealmate.test` ("user B", new for this test), confirms both, and seeds a
minimal `user_profiles` row for each — the test's third case reads user A's own row, so there has
to be one to read. It prints the six `SUPABASE_*` values below; if a user already existed, its
password is unknown (Admin API never returns it) and the script says so rather than guessing.

## 2. Set the GitHub repo secrets

Settings → Secrets and variables → Actions → New repository secret, one per line the script
printed:

```
SUPABASE_URL=<project URL>
SUPABASE_ANON_KEY=<anon public key>
SUPABASE_TEST_USER_EMAIL=<user A email>
SUPABASE_TEST_USER_PASSWORD=<user A password>
SUPABASE_TEST_USER_B_EMAIL=<user B email>
SUPABASE_TEST_USER_B_PASSWORD=<user B password>
```

`SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_TEST_USER_EMAIL`/`SUPABASE_TEST_USER_PASSWORD` likely
already exist from MP-012 (`docs/MP-006-MP-012-supabase-setup.md`) — only the two `_B_` secrets are
new. `.github/workflows/ci.yml`'s mobile job now injects all six into the Jest step and, on any
same-repo run (push, or a same-repo PR — this project takes no external fork PRs), fails the job
with a clear `::error::` before Jest even runs if any are missing.

For local runs, export the same six in your shell (or a local `.env` your shell loads) before
`cd mobile && npx jest rls-cross-user` — never commit them (same convention as `backend/.env`).

## 3. What it proves once it runs for real

- User B querying `user_profiles`/`meal_plans` filtered to user A's id gets back an **empty
  result**, not an error and not user A's data — RLS silently filters rather than 403ing, which is
  the correct Postgres RLS behavior and worth asserting explicitly (a naive test might only check
  "no error" and miss a policy that returns everything).
- User A can still read their own profile row — confirming the policy isn't just failing closed
  for everyone.

## Status

**Not done yet** — this is the one remaining manual step for MP-023's definition of done. Until
someone with dashboard/service_role access runs step 1 and sets the step-2 secrets, the mobile CI
job fails on every push/PR by design (see §0 above) rather than quietly passing without ever really
asserting the cross-user denial.
