# MP-058–064, 071–073 — Phase 7: Swap, Notification Reliability, Favorites, Make-Extra

## Track A — verification (done first, per the brief)

Three things were genuinely unknown after Phase 5/6 and needed a real answer before the rest of
this phase could be scoped with any confidence. All three were run against real code and real
data — not inferred.

**1. The MP-020 blocking gap (non-veg tiffin, Egg+Gluten both excluded).** Ran the actual fallback
logic (`rule_based_fallback.build_fallback_plan`) for a synthetic every-day-non-veg user with
`dietary_restrictions=['Egg','Gluten']`. Result: every morning slot came back `status='filled'`,
never `needs_manual_pick`. The dish picked was a **vegetarian** tiffin substitute (`Plain Dosa`,
`Uttapam` — confirmed `dietary_flags=[]`, so no safety violation) — `build_fallback_plan` silently
relaxes the **non-veg quota** (an advisory-strength constraint) rather than the dietary exclusion
(hard, never relaxed), exactly per MP-047's priority order. The OpenAI path likely never even hits
this as starkly: `nonveg_quota` validation is date-scoped, not slot-scoped, so a real model can
satisfy "this day is non-veg" via the afternoon gravy and leave tiffin vegetarian — not verified
live (would need a real model call), but architecturally sound from reading `menu_validation.py`.

**2. `prep_bias` functional status.** Confirmed by reading `catalog_repo.get_candidates`: no
`ORDER BY`/filter on `prep_minutes` anywhere in MP-034's query. It is used **only** inside the
rule-based fallback's `_rank` tie-breaker. For the 553/573 dishes missing `prep_minutes`, this
isn't "silently ignored" — it's a blanket `10**9` sentinel that **always** deprioritizes them
below any dish with a real value on a `quick` day, regardless of the missing dish's true prep
time. The OpenAI path only receives `prep_bias` as an unenforced prompt instruction with no
validator behind it.

**3. What MP-050/055 actually produce.** Ran the real grocery-snapshot builder
(`plan_persistence.build_grocery_payload`) against an actual seeded week (56 filled plan items,
one of the live test users). Not empty, but seriously incomplete: only 35/56 (62.5%) of that
week's plan items reference a dish with *any* `dish_ingredients` link at all — the other 21
(37.5%) contribute nothing. Output was 18 generic pantry-staple entries, every `quantity` `null`.
A user looking at this list would reasonably assume it reflects their actual week; it mostly
doesn't, because 553/573 catalog dishes still have zero ingredient data (unchanged from Phase 6's
own caveat).

**Risk this changes for the rest of the phase:** none of the three findings changes what Track
B/C/D needed to build — they're pre-existing data/coverage gaps (Phase 5/6), not phase-7 blockers.
Flagged here per the brief's own instruction, not fixed (out of scope this phase).

## Track B — Swap (MP-058/059/060/062)

**Architecture decision, stated explicitly:** the mobile client has no live backend HTTP endpoint
to call for this (confirmed against `docs/version1_mealPlanner_technical.md` §3's own table —
quick-swap is listed as "Postgres RPC / stored function — no LLM call, no Python hop", and no
other live surface exists). `backend/app/services/generation_eligibility.py`'s dietary/eligibility
gate is Python that only ever runs inside scheduled batch jobs, never reachable from a live mobile
request. So the RPCs in `supabase/migrations/0019_plan_item_edit_rpcs.sql`
(`swap_plan_item`, `add_plan_item_to_slot`, `remove_plan_item`, `carry_over_plan_item`,
`list_swap_candidates`) reimplement the *same* array-overlap dietary rule in SQL, cross-referenced
in comments back to the Python module — not a second, divergent filtering path, the same rule
expressed in the runtime that actually executes the mobile client's write.

- **Hard-blocked**: item_type mismatch, dietary conflict, ownership (every RPC re-checks
  `auth.uid()` inside the function body itself, `security definer`, matching the established
  `register_push_token` pattern — RLS alone can't express the validation these writes need).
- **Never hard-blocked**: in-week repeat, 10-day history, non-veg quota — edit-time rules are
  advisory only (functional spec §6), so `list_swap_candidates` surfaces `used_this_week` /
  `used_recently` as informational badges (MP-062), never disabling a candidate row.
- **Mobile**: `WeekPlanScreen.tsx`'s previously-inert `SlotDetailSheet` now offers a real one-tap
  quick swap (MP-059) when a slot has exactly one item (morning/night); a multi-item slot (e.g.
  afternoon's rice+gravy+poriyal) hands off to the newly-built `DayReviewEditScreen.tsx`, which
  supports per-item swap, add, remove, and make-extra carry-over (MP-058/060/064).

**Verified, not just implemented**: a swap attempt that *should* be blocked by an allergen was
actually tested (`test_swap_hard_rejects_a_dietary_conflict_not_just_the_happy_path`,
both the Python integration suite and `rls.test.mjs`'s cross-user version), matching the brief's
explicit demand not to stop at the happy path.

## Track C — Notification reliability (MP-071/072/073)

**MP-071 was already substantially built** in Phase 4/6 (`notification_log`'s
pending→processing→sent/failed lifecycle, `try_claim`'s atomic transition, ticket ID recording) —
confirmed by reading the existing code before assuming new work was needed. No new schema or logic
required here.

**MP-072 — one same-evening retry**: previously there was no actual retry mechanism within a
single run, only a DB-level "a *second script invocation* may reclaim a failed row" allowance.
Added `push_dispatch.send_expo_push_with_one_retry` — an immediate, in-process retry of exactly
one failed send, used by both `run_daily_reminder.py` and `run_weekly_generation.py`'s
`_dispatch_week_ready`. Verified with a test that forces **two** consecutive failures and asserts
no third attempt (`test_two_consecutive_failures_raise_after_exactly_two_attempts_no_third`), per
the brief's explicit AC — a single-failure test alone wouldn't have caught a broken retry-forever
loop.

**MP-073 — Expo receipt reconciliation**: genuinely new. `push_dispatch.get_expo_receipts` calls
Expo's separate `getReceipts` endpoint; `scripts/run_notification_reconciliation.py` finds every
`sent` `notification_log` row (of either type — `daily_reminder` and `week_ready` share this
table) older than a 25-minute buffer, and reconciles it to `delivered` or `failed`. Runs on its
own schedule (`.github/workflows/notification-reconciliation.yml`, 20:40 IST — ~40 min after both
daily sweeps fire), not chained onto either sweep, since a receipt genuinely isn't ready the
instant a ticket is issued.

## Track D — Favorites and make-extra (MP-063/064)

**Favorites cap.** `user_favorite_dishes` already grants direct `insert` to `authenticated`
(0006) — the mobile client can and does write directly, so a Python-only check (which nothing on
the live client path ever calls) would not actually hold the line. Enforced with a
`before insert` trigger (`supabase/migrations/0018_favorites_cap.sql`) instead, which fires
regardless of write path. **Bug found and fixed during testing**: the first version of the trigger
didn't account for re-adding an already-favorited dish — since `ON CONFLICT DO NOTHING` resolves
*after* a `BEFORE INSERT` trigger runs, a user already at the cap couldn't even no-op re-favorite
something they already had. Fixed by checking for the existing `(user_id, dish_id)` pair first.
`profiles_repo.add_favorite` also checks the cap in Python, for backend-driven callers and a
friendlier error than a raw `check_violation`.

**10-day exemption vs. in-week dedup — proven not conflated, not just asserted.** The functional
spec is explicit that a favorite still can't repeat in the same generated week. Added
`test_a_favorite_still_cannot_repeat_within_the_same_generated_week` to `test_menu_validation.py`
(a favorite, `track_variety=true`, placed twice in one week — `in_week_repeat` still fires) sitting
alongside the pre-existing `test_favorites_are_exempt_even_when_served_recently` (10-day exemption)
— together they demonstrate the two rules are handled by entirely separate code paths
(`menu_validation.py` never reads `favorite_dish_ids`; `variety_exclusion.py` is the only place
favorites are subtracted out), so there's no shared logic that could silently conflate them.

**Make-extra.** `plan_items.make_extra` already existed in the schema since Phase 1 (0003) — the
gap was that nothing let the mobile client actually *create* a carried-over item.
`carry_over_plan_item` copies an already-planned (already dietary-safe) dish into another slot,
`make_extra=true`, deliberately skipping the dietary/eligibility re-check (the dish is already
known-safe) and deliberately not touching in-week/history handling — this is the intentional
bypass the brief calls out, not a validation gap.

## Verification performed

- Backend: `ruff check .` / `mypy app/` clean. Full pytest suite (including the new
  `test_plan_item_edit_rpcs.py`, `test_run_notification_reconciliation.py`, and additions to
  `test_repositories.py`/`test_menu_validation.py`/`test_push_dispatch.py`) green against a real
  throwaway Postgres database built from the actual migrations.
- Supabase: all 58 `supabase/tests/rls.test.mjs` + `schema.test.mjs` tests pass (pglite, real
  Postgres semantics), including new cross-user negative-authorization cases for every one of the
  five new RPCs and the favorites-cap trigger, called the way the mobile client actually calls
  them (`asUser`/`asAnon` role switching, not a superuser bypass).
- Mobile: `tsc --noEmit`, `expo lint`, and `prettier --check` clean on every changed/added file.
  `WeekPlanScreen.test.tsx` (13 tests, including 2 new ones covering the single-item quick-swap and
  the multi-item hand-off to `DayReviewEditScreen`) and the new `DayReviewEditScreen.test.tsx` (5
  tests: render, swap-candidates-with-badges, apply-swap, remove-with-revert-on-failure, favorite
  toggle) pass.
- Live smoke test: every new RPC (`swap_plan_item`, `add_plan_item_to_slot`, `remove_plan_item`,
  `carry_over_plan_item`, `list_swap_candidates`) was called directly against the live Supabase
  project with a real test user and real catalog data before the automated tests were written,
  including the dietary-conflict rejection path.

## Known gaps carried forward, not fixed this phase

- MP-017's dietary tagging is still best-effort (Phase 5), and swap reuses that same data — a
  swap-blocked-by-allergen guarantee is only as good as the underlying `dietary_flags` accuracy.
- MP-019's flagged duplicate/weakly-sourced dishes are still in the live catalog; swap/add candidate
  lists can surface them.
- `dish_ingredients` is still ~96% unpopulated (Track A finding #3) — the grocery list stays
  incomplete regardless of what plan the user ends up with via swap/add/remove.
