# MP-001 — v1 Scope Baseline (Approved Draft)

Source of truth: `version1_mealPlanner_functionalities.md` + `version1_mealPlanner_technical.md`.
This freezes the v1 feature boundary per MP-001's acceptance criteria. It restates decisions already
made in the specs — it does not introduce new ones. The four still-open items (MP-002–005) are
tracked separately and are **not** included as frozen scope below.

## In scope for v1

**Core**
- Daily meal plan across 6 slots: morning, afternoon, night, snack_1, snack_2, snack_3.
- Prior-day 8 PM push notification, server-side (outbox pattern: ticket + receipt reconciliation +
  one same-day retry), delivered even if the app is closed.
- 8-question onboarding (functional spec §2), collected once, not editable post-onboarding.
- Dietary restrictions enforced as a **hard code-level exclusion** at generation validation and in
  the rule-based fallback — never left as an LLM instruction alone.
- Tamil Nadu-only dish sourcing from a curated catalog (not generic South Indian, not live LLM
  generation).
- No dish repeat within a rolling 10-day window, scoped per `track_variety` dish — resolved: applies
  against history *and* within the generated week; staples (`track_variety = false`) exempt globally;
  favorites exempt from the 10-day rule only, per user.

**Planning modes**
- Two modes, chosen at onboarding, not switchable in v1: **Suggestion** (default) and **Reserves**
  (opt-in). Same 8 PM daily sweep drives both; trigger offset differs (`grocery_day − 1` vs.
  `grocery_day + 1`).
- Reserves-only ingredient availability: v1 manual checklist (~40–60 produce items); v2 photo
  identification is explicitly out of this phase (see Non-goals).

**Generation & editing**
- Weekly batch generation (one LLM call/week/user), constrained to a pre-filtered candidate catalog,
  validated on 6 criteria (candidate membership, in-week no-repeat, 10-day exclusion, combo template,
  dietary-flag hard reject, quota match), with a deterministic rule-based fallback after one failed
  retry.
- Weekly review/edit: no approval gate, every edit autosaves and is immediately live; item-level
  swap/add/remove; skip/eating-out toggle; edit-time rules are advisory (soft indicators only).
- Quick single-slot swap — served from the already-filtered candidate list, no LLM call.
- "Make extra" / repeat-slot flag — one boolean, bypasses no-repeat deliberately.
- Time-budget tagging (prep-time bias, weekday vs. weekend) — filter on existing data, no new
  functionality.
- Regenerate-remaining-week — reuses the weekly generation path with a `start_date` argument.

**Grocery list**
- Auto-generated, de-duplicated, quantity-aggregated weekly list — top-priority productivity feature.
- Frozen snapshot at "week ready" time (`grocery_list_snapshot`), not a live rollup; post-snapshot
  edits get a "not in this week's shop" badge instead of rewriting history.
- Reserves mode adds shortfall/top-up and catalog-gap badging on top of the same snapshot mechanism;
  Suggestion mode's snapshot is the full list with no availability baseline.

**Favorites**
- Per-user list, exempt from the 10-day rule only (still subject to in-week duplication), capped at
  an estimated 5–8 (tunable — see MP-004 for acquisition path, still open).

## Explicit non-goals for v1

- No quantity/weight estimation from grocery photos.
- No pantry inventory tracking, separate from the weekly grocery-photo/manual list.
- No fine-grained nutrition or macro tracking.
- No mode switching after onboarding (Suggestion ⇄ Reserves).
- No photo-based ingredient identification in this phase — v2, additive on top of the v1 manual
  checklist UI, not a blocker to it.
- No live/on-demand LLM dish generation outside the curated-catalog-constrained flow.
- No festival-calendar-aware suggestions (explicitly noted as a real future feature, not v1-scoped).
- No automated alerting/dashboards beyond `notification_log`'s raw telemetry.
- No circuit breaker / backoff-jitter tuning / dead-letter alerting for external service failures.
- No job queue / worker pool (deferred until concurrent-generation volume approaches Supavisor/TPM
  limits — not a fixed user-count trigger).
- Accept/skip preference learning — **optional, explicitly flagged as the first cut candidate if
  scope needs to tighten**; final v1-vs-deferred call is MP-002, not resolved here.

## Still open (tracked separately, not frozen by this document)

| Task | Decision | Status |
|---|---|---|
| MP-002 | Accept/skip preference weighting: v1 or deferred | Open |
| MP-003 | Curated catalog target count (150–300 range) | Open |
| MP-004 | Favorites acquisition path (onboarding / over-time / both) | Open |
| MP-005 | Notification delivery SLO | Open |

MP-006 onward should not treat these four as settled until each has an explicit recorded decision.

## Traceability

Everything above is sourced from the functional spec (§§1–7) and technical spec (§§1, 4, 5, 5.1, 6,
7) — no scope invented here. The one item the functional spec listed as previously open (10-day
repeat: global vs. per-slot) is already marked "resolved" in functional spec §8 and is restated above
as decided, not re-opened.
