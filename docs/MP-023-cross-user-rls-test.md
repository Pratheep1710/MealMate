# MP-023 — Cross-User RLS Denial Test Setup (manual, owner-only step)

`mobile/src/lib/__tests__/rls-cross-user.test.ts` proves MP-013's RLS policies hold from the
actual mobile client path (supabase-js + a real signed-in JWT), not just from the backend's
pglite-based suite (`supabase/tests/rls.test.mjs`) or a service-role connection. Like
`backend/tests/test_supabase_auth.py` (MP-012), it **skips** rather than fails until a live
project and test users exist — this doc is what turns it into a real assertion.

## 1. Provision a second test user

MP-006/MP-012 already walks through creating **one** confirmed test user. This test needs a
**second**, distinct one:

1. Dashboard → Authentication → Users → Add user (email + password), confirmed. This is "user B";
   whichever user MP-012 already provisioned is "user A".
2. Both users need a `user_profiles` row (the test's third case reads user A's own row — RLS lets
   a user read their own profile, but there has to be one to read). Easiest path: sign in as each
   user once with the mobile app's onboarding flow once it exists (MP-024), or insert a minimal
   row directly via the SQL Editor for now:
   ```sql
   insert into user_profiles (id, grocery_day) values ('<user-a-uuid>', 'monday');
   insert into user_profiles (id, grocery_day) values ('<user-b-uuid>', 'monday');
   ```
   (User ids are visible in Authentication → Users.)

## 2. Set the env vars

```
SUPABASE_URL=<project URL>
SUPABASE_ANON_KEY=<anon public key>
SUPABASE_TEST_USER_EMAIL=<user A email>
SUPABASE_TEST_USER_PASSWORD=<user A password>
SUPABASE_TEST_USER_B_EMAIL=<user B email>
SUPABASE_TEST_USER_B_PASSWORD=<user B password>
```

Export them in your shell before running `cd mobile && npx jest rls-cross-user`, or add them to a
local `.env` your shell loads — never commit them (same convention as `backend/.env`).

## 3. What it proves once it runs for real

- User B querying `user_profiles`/`meal_plans` filtered to user A's id gets back an **empty
  result**, not an error and not user A's data — RLS silently filters rather than 403ing, which is
  the correct Postgres RLS behavior and worth asserting explicitly (a naive test might only check
  "no error" and miss a policy that returns everything).
- User A can still read their own profile row — confirming the policy isn't just failing closed
  for everyone.

Not run in CI (no live project credentials there) — this is a manual/local verification step, same
tier as MP-012's live auth test.
