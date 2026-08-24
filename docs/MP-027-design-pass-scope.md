# MP-027/028 — Claude Design Pass: What Got Built, What Didn't, and Why

Source: claude.ai/design project `b56ee743-b4e9-4d39-a6b7-ff431c2c3f66` ("Meal Planner.dc.html" +
its design brief, `uploads/meal-planner-claude-design-brief.md`). The brief scoped three screens —
weekly plan view, review/edit, and the evening-before push notification — plus a token system (a
"day spine" layout, Newsreader/Hanken Grotesk type pairing, a Tamil Nadu-grounded palette named
after kitchen objects: ink/leaf/turmeric/steel/ground). This doc records what actually shipped
against that brief and, per the same pattern as `MP-015`/`MP-017`, what was deliberately left out
and why — not silently.

## What shipped

- **Design tokens** (`mobile/src/theme/tokens.ts`): the full palette, spacing, radii, and the
  Newsreader/Hanken Grotesk font families, loaded via `@expo-google-fonts/*` at the app root
  (`App.tsx`) behind a splash-screen hold so no screen flashes the system font.
- **`WeekPlanScreen` (MP-027), fully redesigned**: the "day spine" for today (6 slots, real
  RLS-scoped `meal_plans`/`plan_items` reads — no mocked data), a rolling six-day "rest of the
  week" view, the pending ("still cooking") skeleton state for a day with no plan yet, and an
  offline state that falls back to the last successful fetch (cached via AsyncStorage,
  `mobile/src/lib/weekCache.ts`) rather than a bare error.
- Bottom tab labels/icons relabeled to match the design's voice (Week / List / You), reusing the
  existing three tabs — no new tab was added.

## What's real vs. inert, and why

The design's swap/skip/regenerate interactions ("New ideas", tapping a slot, per-part swap) are
wired in the mockup to a ~40-dish dictionary invented for the prototype. None of that exists for
real yet:

- The `dishes` catalog table is empty — still blocked on the missing workbook (`MP-015`).
- There is no generation engine to call for "something else" (`MP-034`/`038-044`, also blocked).
- `meal_plans` is deliberately client-read-only in RLS (`0006_rls_policies.sql`) — skip/eating-out
  can only be written by a backend job, and no API route for that exists yet (`MP-030`'s FastAPI
  skeleton has no routes beyond a health check).

Rather than fake this with the mockup's invented dish list, every edit affordance is visually
present but opens a short, calm, honest sheet ("Once the dish list is ready, this will find
something new for you") instead of performing a no-op action that would look broken. This was a
deliberate scope choice, confirmed before implementation — see the option chosen: "build the full
visual redesign, disable edits."

## What was left out of this pass entirely

- **The evening-before push notification.** The design specs its content and action buttons in
  detail, but there is no push infrastructure in this codebase at all yet (no `expo-notifications`,
  no server-side send path — `docs/MP-001`'s "Core" bullet on this is still unbuilt). Building that
  is a separate, substantial piece of work, not a screen-level styling pass. The design's copy and
  layout are a ready reference for whenever that infrastructure lands.
- **Per-dish prep tips** (e.g. "One cooker whistle does both."). The mockup's notes come from a
  small hardcoded dictionary keyed by its invented dish names — there's no equivalent field on
  `dishes` or `plan_items` in the real schema, and matching against real (future) catalog dish names
  would be guesswork. Slot detail omits this line rather than inventing content.
- **Grocery list.** The design brief explicitly excludes it ("deprioritized for now... don't design
  this"); `GroceryListScreen` was left untouched.
- **A rolling six-day window vs. the app's earlier Monday-anchored week.** The design frames the
  plan as "today" plus the next five days rather than a fixed calendar week. MP-027's first pass
  (before this design existed) used a Monday-anchored week; this pass switches the *display* to the
  rolling model (`mobile/src/screens/weekPlan/rollingDays.ts`), independent of
  `grocery_list_snapshot`'s Monday-anchored `week_start` storage key (`mobile/src/lib/week.ts`,
  untouched) — the two were already independent concerns, and nothing else depended on the display
  choice.
