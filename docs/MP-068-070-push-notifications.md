# MP-068/070 — Push Token Registration and the Daily Reminder Job

Same pattern as `docs/MP-023-cross-user-rls-test.md`: what's built, what's real vs. still a manual
step, and exactly what to do about the manual part.

## What's built

- **MP-068 — token registration.** `mobile/src/lib/pushRegistration.ts` requests notification
  permission, gets an Expo push token, and registers it via the `register_push_token(text)` RPC
  (`0013_push_tokens_schema.sql`) rather than a direct table write. A plain RLS-scoped client
  insert/update (the `plan_items` pattern) can't handle the device-handoff case: Postgres requires
  the pre-existing row to pass a *SELECT* policy before an UPDATE's `WHERE` can match it or an
  `ON CONFLICT DO UPDATE` can detect the conflict, and `push_tokens_select_own` denies exactly the
  row a handoff needs (it still belongs to the *other*, not-yet-current user) — see 0013's
  migration comment. The RPC is `security definer` and hardcodes the caller's own `auth.uid()`
  server-side, so there's no user id argument for a caller to get (or fake) wrong. Wired to fire
  once per session from
  `MainTabNavigator` (`usePushRegistration`, `mobile/src/lib/usePushRegistration.ts`), i.e. only for
  a signed-in, fully onboarded user. Every failure mode (simulator, permission denied, no project
  id, offline) is a silent no-op — see the gap below for why "no project id" is expected right now.
- **MP-070 — the actual send.** `backend/scripts/run_daily_reminder.py`: for every user with a
  registered token, reads *tomorrow's current* plan (`plans_repo.get_day_plan_with_dishes` —
  reflects edits/skips made after generation, not a frozen copy), composes "Tomorrow's dinner idea:
  [dish]" copy (`app/services/reminder_copy.py` — never "plan", and a neutral line if the slot is
  skipped, matching `docs/MP-027-design-pass-scope.md`'s low-pressure framing), claims the
  `notification_log` row (`app/jobs/entrypoints.py`'s existing `run_daily_reminder_dispatch`), and
  sends via Expo's HTTP push API (`app/services/push_dispatch.py`) if
  `app/jobs/entrypoints.py`'s `should_send_reminder` says it's still worth sending (not already
  sent; at most one retry same-day, per docs/MP-001). Scheduled by
  `.github/workflows/daily-reminder.yml` at 20:00 IST (14:30 UTC, fixed — India has no DST).

## Gap: MP-068 needs an EAS project id

`Notifications.getExpoPushTokenAsync()` requires `projectId` once running outside Expo Go (SDK 57).
This repo has no `eas.json`/linked EAS project yet, so `getProjectId()` in
`pushRegistration.ts` currently returns `undefined` and registration no-ops rather than crashing.

**To actually receive a token on a device:**
1. `npx eas init` from `mobile/` (creates the EAS project, writes the project id into
   `app.config.ts`'s `extra.eas.projectId` — or set it manually if you already have a project id).
2. Build a dev client or EAS build — push tokens are unavailable in Expo Go on Android from SDK 53
   onward, and are unreliable there generally; a real device (not a simulator) is required either
   way (`Device.isDevice` gates registration for exactly this reason).
3. Sign in on that device/build and confirm a row appears in `push_tokens`.

I don't have an Expo/EAS account or a physical device in this session to complete that step —
flagging it explicitly per this phase's "flag what I had to assume" instruction, same as MP-023's
outstanding manual step.

## New repo secrets MP-070's workflow needs

`.github/workflows/daily-reminder.yml` needs everything `app/config.py`'s `load_config()` requires
(it validates all groups, not just the ones this script touches) plus the Expo access token:

```
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_DB_HOST
SUPABASE_DB_PORT        (optional, defaults to 5432)
SUPABASE_DB_USER        (optional, defaults to "postgres")
SUPABASE_DB_PASSWORD
OPENAI_API_KEY
OPENAI_MODEL
EXPO_ACCESS_TOKEN       (only required if the Expo project has Enhanced Push Notification
                         Security turned on — see app/config.py's ExpoConfig)
```

`SUPABASE_URL`/`SUPABASE_ANON_KEY` likely already exist from MP-012
(`docs/MP-006-MP-012-supabase-setup.md`); the `SUPABASE_DB_*`/`SUPABASE_SERVICE_ROLE_KEY`/
`OPENAI_*` values are new for this workflow specifically (the existing `ci.yml` job never needed
direct DB or OpenAI credentials).

## Status

Registration and send code are written and unit-tested (`mobile/src/lib/__tests__/
pushRegistration.test.ts`, `backend/tests/test_reminder_copy.py`, `backend/tests/
test_push_dispatch.py`, `backend/tests/test_jobs.py`'s `should_send_reminder` cases). **Not
verified end-to-end** — that needs the EAS project id above, the repo secrets above, and a manual
`workflow_dispatch` run (or waiting for the schedule) against a device that actually registered a
token. Until then, `run_daily_reminder.py` will run and log correctly against an empty
`push_tokens` table (zero users to notify) but has not been proven to deliver a real push to a real
phone.
