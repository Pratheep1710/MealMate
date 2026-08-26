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
- **MP-068 — unregistration on sign-out.** PR #10 review fix: `unregister_push_token(text)`
  (`0014_push_token_unregister.sql`) is called from `SessionContext.signOut()` — before
  `supabase.auth.signOut()`, since it needs `auth.uid()` to still resolve — so a signed-out device
  stops receiving the outgoing user's reminders instead of continuing to until someone else signs
  in on it.
- **MP-070 — the actual send.** `backend/scripts/run_daily_reminder.py`: for every user with a
  registered token, reads *tomorrow's current* plan (`plans_repo.get_day_plan_with_dishes` —
  reflects edits/skips made after generation, not a frozen copy), composes "Tomorrow's dinner idea:
  [dish]" copy (`app/services/reminder_copy.py` — never "plan", and a neutral line if the slot is
  skipped, matching `docs/MP-027-design-pass-scope.md`'s low-pressure framing), and sends via
  Expo's HTTP push API (`app/services/push_dispatch.py`) if `app/services/reminder_claim.py`'s
  `claim_reminder` won the atomic `pending`/retryable-`failed` → `processing` transition
  (`notifications_repo.try_claim`, `0015_notification_log_claim_status.sql` — PR #10 review fix:
  the original check-then-send was non-atomic, so two overlapping runs could both send the same
  reminder; this closes that the same way `generation_claim.py` closes it for weekly generation).
  Scheduled by `.github/workflows/daily-reminder.yml` at 20:00 IST (14:30 UTC, fixed — India has no
  DST) — **live as of PR #11**: the `schedule:` trigger is enabled.

## MP-068 end-to-end device verification — done (PR #11)

`Notifications.getExpoPushTokenAsync()` requires `projectId` once running outside Expo Go (SDK 57),
plus real Android push needs Firebase Cloud Messaging (FCM) V1 credentials — neither existed as of
PR #10. Both are now set up:

- EAS project linked (`app.config.ts`'s `extra.eas.projectId`, `owner`, `slug`); Android
  `package: com.pratheeplabss.mealplanner`.
- A Firebase project ("MealPlanner") registered under that same package name.
  `google-services.json` is *not* committed (gitleaks flags its embedded API key, and Google's own
  guidance not to rely on secrecy for it doesn't change that this repo's security gate should still
  hold) — it's stored as an EAS file-type environment variable (`GOOGLE_SERVICES_JSON`), which
  `app.config.ts`'s `android.googleServicesFile` reads via `process.env.GOOGLE_SERVICES_JSON` at
  build time, falling back to a local gitignored copy for `expo start`.
- The FCM V1 service account key is uploaded via `eas credentials -p android` → **Google Service
  Account → Push Notifications (FCM V1)** (not the *Legacy* slot — easy to pick by mistake, and the
  wrong one silently accepts the same file without ever powering a real send).
- Verified on a real Android device: signed in, permission granted, a real `ExponentPushToken[...]`
  row appeared in `push_tokens`, and — app fully force-closed — a push sent via
  `send_expo_push` was received as a real system notification.
- `unregister_push_token` was exercised the same session (sign-out removes the device's row).

## New repo secrets MP-070's workflow needs

`.github/workflows/daily-reminder.yml` needs everything `app/config.py`'s `load_config()` requires
(it validates all groups, not just the ones this script touches) plus the Expo access token:

```
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_DB_HOST
SUPABASE_DB_USER        (optional, defaults to "postgres" — this project's pooler host needs
                         "postgres.<project-ref>", so it's set explicitly rather than relying on
                         the default)
SUPABASE_DB_PASSWORD
OPENAI_API_KEY
OPENAI_MODEL
EXPO_ACCESS_TOKEN       (only required if the Expo project has Enhanced Push Notification
                         Security turned on — see app/config.py's ExpoConfig)
```

**Do not create a `SUPABASE_DB_PORT` secret.** An unset GitHub Actions secret resolves to an empty
string, not an absent env var — `app/config.py`'s "fall back to the 5432 default" only recognizes
truly-missing vars, so an *empty* `SUPABASE_DB_PORT` fails int validation instead of defaulting
(caught by PR #11). The workflow simply omits the line; the default is correct.

`SUPABASE_URL`/`SUPABASE_ANON_KEY` likely already exist from MP-012
(`docs/MP-006-MP-012-supabase-setup.md`); the `SUPABASE_DB_*`/`SUPABASE_SERVICE_ROLE_KEY`/
`OPENAI_*` values are new for this workflow specifically (the existing `ci.yml` job never needed
direct DB or OpenAI credentials).

## Status

Fully verified end-to-end as of PR #11: registration, unregistration, the atomic send claim, and
the send itself are all written and tested (`mobile/src/lib/__tests__/pushRegistration.test.ts`,
`mobile/src/contexts/__tests__/SessionContext.test.tsx` — unregister-before-signOut ordering,
`supabase/tests/rls.test.mjs` — register/unregister RLS including cross-user denial,
`backend/tests/test_reminder_copy.py`, `backend/tests/test_push_dispatch.py`,
`backend/tests/test_reminder_claim.py` — including a real two-connection race, mirroring
`test_generation_claim.py`), *and* proven live: a real device registered a token, received a real
push with the app closed, and a `workflow_dispatch` run of `daily-reminder.yml` against the fixed
branch completed successfully (`sent`/`skipped` as expected, no errors). The schedule is enabled.
