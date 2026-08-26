# Meal Planner — Functional Spec (v1)

Personal-use meal planning app, Tamil Nadu cuisine, LLM-driven menu generation. Built to scale to multi-user later without a schema rework.

---

## 1. Core scope (original requirements)

- Daily meal plan across 6 slots: morning, afternoon, night, + 3 snacks.
- Prior-day notification at 8 PM local time, delivered even if the app is closed (requires server-side push, not on-device scheduling).
- Onboarding collects user context for personalization: weekly non-veg quota and which specific days, plus any dietary restrictions.
  - **Dietary restrictions/allergies are a hard exclusion, enforced in code, never just an instruction handed to the LLM.** An allergen slip is a safety issue, not a quality one — treated accordingly throughout generation and fallback (see technical doc §5).
- LLM used for reasoning and composing the day's/week's menu — not as the source of dish knowledge (see §4).
- All suggested dishes are Tamil Nadu based (not generic South Indian).
- No dish repeats within a rolling 10-day window.
  - **Open decision:** tracked per dish globally across all slots (default assumption) vs. scoped per slot-type. Confirm before building the history query.

---

## 2. Onboarding

Collected at account setup (first time only), 8 questions:

1. How many days a week do you eat non-veg?
2. Which specific days?
3. Any dietary restrictions or allergies?
4. Dinner style — full rice meal, or tiffin-style?
5. "You'll tell us what you bought each week" or "We'll give you a shopping list each week" — plain-English only; "Reserves mode" and "Suggestion mode" are internal names, never shown to the user. Defaults to the shopping-list option (Suggestion) if skipped or the answer is ambiguous — matches the mental model most people bring to a meal-planning app and needs zero prep before the first plan. Reserves is the opt-in for someone who already knows they want it.
6. Which day do you usually do grocery shopping?
7. Start your first plan today, or begin on [the actual computed next-cycle date, shown concretely — not the word "cycle," which means nothing to a first-time user]?
8. Any favorite dishes to prioritize? (optional, skippable — seeds the favorites list, see §6)

Answers to 6 and 7 drive scheduling directly (see §3) rather than just personalizing content — signing up mid-week shouldn't mean several days of an empty app. Answer to 5 changes *which direction* §3's scheduling runs, not just whether ingredient data gets collected. **Not changeable after onboarding in v1** — mode switching raises real questions (what happens to a mid-week plan, what happens to accumulated ingredient data going reserves→suggestion) that aren't worth solving before an actual user asks for it. Stated as a deliberate v1 constraint, not an oversight.

---

## 3. Generation & scheduling

- **Weekly batch generation**, not nightly. Full week generated in one LLM call.
  - Trigger direction depends on planning mode (§2), not just whether ingredient data exists. Both run off the same fixed 8 PM daily sweep — no second cron, just a different offset check:
    - **Reserves mode** — generation runs the day *after* `grocery_day`, so the plan reflects what's actually on hand.
    - **Suggestion mode** — generation runs the day *before* `grocery_day`, at 8 PM, so the list is ready overnight for that morning's shop. Generating "on `grocery_day` itself" doesn't work — by 8 PM the day's shopping is already done, and the list would arrive too late to be useful, which defeats the entire point of this mode.
  - **"Start today" in Suggestion mode**: the immediate generation produces its own grocery-list snapshot (§6) at the moment it's created, exactly like the normal weekly cycle — no special case, just an off-cycle trigger. The user shops today for the partial week (e.g. Wed–Sun) using that list; an explicit "start today" is itself a signal of readiness to act now.
  - **"Start today" in Reserves mode**: a brand-new user has no "grocery day already happened" moment to draw from, so the immediate generation needs an immediate ingredient checklist first — the same v1/v2 flow from §5, just triggered by signup instead of the next `grocery_day`.
  - Weekly non-veg quota and 10-day variety constraints are reasoned about holistically in one pass, rather than incrementally guessed each evening.
  - The 8 PM daily job becomes a **reminder push** pulling from the already-computed (and possibly already-edited) plan, not a fresh generation call.
  - Trade-off: less last-minute adaptability — mitigated by the quick-swap feature (§4) and the review/edit flow (§6).
- Dish selection is constrained, not freely generated: a curated dish database (150–300 dishes tagged by meal-slot, veg/non-veg, region/style, ingredients, prep time) is filtered by the day's constraints first; the LLM composes/reasons over the filtered candidates and returns structured output. This avoids hallucinated or non-regional dishes and keeps token cost low. Ingredient-availability filtering is one such constraint, and it's the one that's mode-dependent — see §5.

---

## 4. Productivity features (beyond the original ask)

Ranked by time actually saved:

1. **Weekly grocery list** — auto-generated, de-duplicated, ingredient quantities aggregated across the week's plan. Top-priority feature; converts the plan into something actionable at the store. No new AI work — a rollup query over already-structured dish/ingredient data.
2. **Quick single-slot swap** — reject one slot, get a replacement without touching the rest of the day/week. Served from the already-filtered candidate list at generation time — **no LLM call**, near-instant, zero marginal cost.
3. **"Make extra" / repeat-slot flag** — intentionally repeat a dish in the next slot (e.g. bulk-cooked sambar reused for lunch and dinner), deliberately bypassing the no-repeat rule. One boolean on the plan entry.
4. **Time-budget tagging** — dishes tagged with prep time; weekday slots biased toward quicker dishes, weekends can carry more elaborate ones. Uses data already captured for the grocery feature; it's a filter change, not new functionality.
5. **Accept/skip signal** *(cut candidate for tighter v1 scope)* — lightweight per-slot feedback ("made this" / "skipped this") that nudges a dish's ranking weight up or down for future eligibility. Not a recommendation engine — a single weight column adjusted on read. Useful because otherwise personalization never evolves past the onboarding questionnaire.
6. **Regenerate remaining week** — a one-tap replan for the rest of the week (e.g. Wed–Sun) after a disruption: guests, illness, three days of eating out. Reuses the existing weekly generation path with a start-date argument instead of always Monday — cost is one LLM call and a button, nothing new to build. This is the retention feature: someone whose week fell apart on day 2 and has no easy recovery path is the person who quietly stops opening the app, which defeats the point of a planning tool more than any single missing feature would.
   - No new mechanism needed per mode — both reuse machinery already built. **Reserves mode** stays within the current `available_ingredients` (regenerate is disruption recovery, not a new shopping trip; if candidates run out, the existing fallback `needs_manual_pick` state surfaces exactly as it would on any normal generation). **Suggestion mode** produces a fresh grocery-list snapshot for the regenerated days, badged against the original via the same post-snapshot delta mechanism from §6 — a regenerate is, from the system's point of view, just a bulk edit.

---

## 5. Ingredient planning — Reserves mode only

Everything in this section applies **only to users in Reserves mode** (§2 onboarding). Suggestion-mode users skip it entirely — no checklist, no photo step, nothing to fill in before their plan generates.

**Sequencing decision:** manual ingredient selection ships first (v1); photo identification layers on top later (v2) as a pre-fill for the same UI, not a separate feature.

### v1 — Manual ingredient selection
- Searchable checklist of the produce ingredients that appear across the dish catalog (~40–60 items).
- User taps what they bought Saturday; list feeds directly into the weekly generation prompt as available-ingredient context.
- No AI cost beyond the existing weekly generation call — this is a few extra tokens on an already-planned call, not a new one.
- 100% accuracy since the user entered it directly.

### v2 — Photo-based identification
- User photographs the grocery haul (one or more shots).
- Vision-capable LLM call produces a **draft** ingredient list — never treated as final.
- **Mandatory confirm/edit step** before the list is used: pre-checked items, tap to remove misidentifications, add anything missed. This step reuses the exact checklist UI from v1.
- Fallback: if a photo comes out unusable, user skips straight to manual selection (v1 path) — the photo path is additive, never the only way in.
- Cost is not the constraint here — it's a once-a-week call, so even a non-trivial vision call cost is negligible annually. The real risk is misidentification of regional produce (drumstick, snake gourd vs. ridge gourd, greens varieties, raw banana, small brinjal varieties), which is why the confirm step is non-negotiable rather than a nice-to-have.

### Rules for both paths
- **Staples excluded from matching** — rice, dal, oil, basic spices assumed always available. Requires dishes' ingredients to be tagged staple vs. produce.
- **Presence only, not quantity** — boolean "have it" vs. weight/quantity estimation. Quantity precision is a different, harder problem (weighing, receipt OCR) deferred indefinitely unless proven necessary.
- **Shortfall handling** — if available ingredients don't cover all 7 days, the system explicitly surfaces which days need a top-up and what to buy, rather than silently picking a mediocre dish or silently dropping the ingredient constraint.
- **Catalog gap flag** — if an identified/selected ingredient has no cataloged dish, flag it ("no recipe on file for X") instead of silently ignoring it. Surfaces dish-catalog gaps as visible signal.

### Suggestion mode's grocery list, for contrast
No availability input exists, so there's no "shortfall" or "top-up" framing — the list is simply everything the generated plan needs, in full, since nothing was assumed already on hand. Same snapshot-at-generation-time mechanism as Reserves mode (§6), just without the gap-highlighting layer on top.

---

## 6. Weekly review & edit

Generated per the schedule in §3; user reviews and can edit any slot through the week before shopping/cooking.

- **"Your week is ready" notification** — separate push, fired when weekly generation completes. Distinct from the daily reminder push.
- **No approval step.** Each edit saves immediately and becomes the live version used for the grocery list and every subsequent notification — there's no separate "confirm the week" action gating anything. Simpler for the user, and consistent with the edit-time philosophy below: the user's action *is* the confirmation, a second explicit approval would just be friction restating a decision already made.
- **Item-level editing** (slots are composed combos, see §5-note): tap an item to swap it for an alternative of the same `item_type`; `+` to add a missing item_type; remove an item without replacing it.
- **Skip / eating-out toggle per slot** — marks a slot as not cooked. Drops its items from the grocery list and excludes them from variety/history tracking, since nothing was actually made.
- **Rule strictness differs between generation and editing, deliberately:**
  - At **generation time**, the no-repeat and quota rules are strict guardrails on the LLM — they keep unsupervised output sensible.
  - At **edit time**, they're advisory only. The user can freely repeat a dish or exceed a stated quota; the app shows a soft, dismissible indicator ("used in the last 10 days" / "4th non-veg day this week") rather than blocking the action. A human explicitly choosing something is the supervision — the same restriction would just be friction at that point.
- **Favorites** — a per-user list of dishes exempt from the no-repeat rule, same mechanism as the global staple exemption (rice/curd) but user-specific. Capped at roughly 5–8 dishes (estimate, to be tuned against real usage) and exempt from the 10-day history rule only — a favorite still can't appear twice in the *same* week, so the basic variety guarantee holds even with a full favorites list. Applies both at generation time (LLM can place a favorite more freely) and at edit time (no indicator shown at all). A plain manual edit (repeating a dish without marking it a favorite) still logs into the normal 10-day history for next week's generation; a marked favorite doesn't.
- **Grocery list is frozen at "week ready" time, not a live rollup.** Correction from the earlier version of this doc: a pure live rollup breaks once shopping has actually happened — an edit made Monday would silently rewrite what Saturday's shop was supposed to cover. The list the user shops from is a snapshot taken when the week is generated; edits made afterward that introduce a new ingredient get a "not in this week's shop" badge instead of invisibly changing the historical list. Edits are still never restricted — this only affects what's shown as "already covered" vs. "you may need this too." Same snapshot mechanism in both planning modes (§5) — only Reserves mode adds shortfall/gap badging on top; Suggestion mode's snapshot is just the full list, since there was never an "already have" baseline to badge against.

---

## 7. Explicit non-goals for v1

- No quantity/weight estimation from photos.
- No pantry inventory tracking (separate from weekly grocery-photo/manual list).
- No fine-grained nutrition or macro tracking.
- Accept/skip preference learning is optional — cut first if scope needs to tighten.

---

## 8. Open decisions to confirm before technical design

- 10-day no-repeat: global per dish, or scoped per slot-type? — *resolved: applies per `track_variety` dish, both against the 10-day history and within the generated week itself; rice/curd and other staples are exempt globally; favorites are exempt per-user.*
- Whether the accept/skip signal ships in v1 or is deferred.
- Exact list of produce ingredients / dish count for the initial curated catalog (drives both onboarding scope and grocery-photo matching coverage).
- Whether "favorites" is collected at onboarding, built up over time via the accept/skip signal, or both.
