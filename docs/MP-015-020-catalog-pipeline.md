# MP-015–020 (Catalog track) — Taxonomy, Ingestion, Ingredients, and the Coverage Gate

Phase 5. Supersedes `docs/MP-015-catalog-blocked.md` (which was accurate at the time — the
workbook genuinely wasn't in the repo tree yet) — the real
`Tamil_Nadu_Dishes_Master_Catalogue_Claude.xlsx` (690 rows, "Master Dishes" sheet) was found on
disk this phase and is what everything below runs against. Still not committed to the repo (it
never has been) — every script here takes its path as an argument.

## PR #12 review round — 5 findings, all fixed, live catalog corrected

Four CI-passing but real correctness/safety gaps found on first review, each fixed and re-verified
against the live database (all numbers below already reflect the corrected data, not the original
run):

1. **[P1] `user_profiles.dietary_restrictions` had no matching constraint or casing guarantee.**
   `dishes.dietary_flags` uses `Nuts`/`Milk-Dairy`/etc., but the profile column that will eventually
   feed `exclude_dietary_flags` was left free-form — a profile value of `"nuts"` would never
   array-overlap a dish tagged `"Nuts"` (Postgres array overlap is case-sensitive), silently
   defeating the hard exclusion once MP-034 wires this up. Fixed with a new migration
   (`0017_user_profiles_dietary_restrictions_vocabulary.sql`, backfill-then-constrain, mirroring
   0016), a matching Pydantic validator on `UserProfile.dietary_restrictions` (and, for symmetry,
   on `Dish.dietary_flags` too — both now import the one shared `DIETARY_FLAG_VALUES` constant from
   `app/models/dish.py`), and a real end-to-end test
   (`test_repositories.py::test_a_real_user_profiles_dietary_restrictions_actually_excludes_a_matching_dish`)
   that writes a profile, reads it back, and proves its own `dietary_restrictions` value actually
   excludes a matching dish through `get_candidates` — not just that both sides independently accept
   the same vocabulary.
2. **[P1] `track_variety` was never corrected for the 553 pre-existing workbook rows.** The original
   `ON CONFLICT` update omitted `track_variety` entirely, so every rice/curd dish that had only ever
   received the schema default (`true`) stayed wrong forever — 36 rice dishes never got flipped to
   `false`. Fixed one-directionally in `ingest_catalog.py`'s upsert: an existing `true` is corrected
   to `false` when the systematic rule says so (an unset default drifting to its real value), but an
   existing `false` is never touched (the schema default is `true`, so a `false` can only exist
   because something deliberately set it — e.g. `dev_placeholder_dishes.sql`'s murukku/payasam
   exceptions — and this systematic pass must not clobber that). Re-run live: rice dishes went from
   1/37 correctly `false` to 35/37 (the remaining 2 — `Lemon Rice`, `Tomato Rice` — are
   placeholder-only names that don't exist in the workbook at all, so the pipeline correctly never
   touches them either way). Two new tests cover both directions of this rule.
3. **[P1] MP-020 only checked one excluded flag at a time.** A catalogue can pass every single-flag
   check while still having zero candidates for a user excluding two flags simultaneously —
   exactly what a real multi-allergy profile does via `exclude_dietary_flags`, which takes a whole
   list at once. Rewrote `validate_coverage.py` to fetch each `(item_type, veg_or_nonveg)` group's
   dietary_flags once and check every combination of the 6-flag vocabulary in memory (not one SQL
   query per subset), reporting only the *minimal* failing combinations so a superset of an
   already-failing set doesn't bury the report in redundant noise. **This found a real, previously
   invisible gap**: `tiffin / nonveg` passes every single-flag exclusion but has zero candidates for
   a user excluding both `Egg` and `Gluten` together — see the updated MP-020 section below.
   MP-034's actual per-slot combo templates still don't exist, so this remains scoped to the
   item_type × diet × flag-combination cross product, same limitation as before — just no longer
   blind to simultaneous restrictions within that scope.
4. **[P2] MP-019's sourcing check silently skipped rows with no source URL at all**, and only
   matched the one literal phrase "south-indian". A missing citation is a *worse* failure of
   MP-003's traceability requirement than a generic one, not something to ignore. Renamed
   `find_generic_sourced` → `find_non_tamil_specific_sourced` and broadened it: flags a row if its
   Source URL is missing/blank, or present but doesn't mention Tamil Nadu at all (not just the one
   known phrasing). Re-run against the real workbook: still exactly the same 77 rows (0 missing-URL
   rows exist in this particular workbook) — same result, materially more defensible check.
5. **[P2] Allergen/meat-type keyword matching was raw substring, not word-boundary.** `"til"`
   matched inside `"lentil"`, `"egg"` inside `"eggplant"`, `"atta"` inside `"pattani"` (Tamil for
   green peas) — each a real false-positive risk against this catalogue's actual ingredient text.
   Fixed with a `_contains()` helper using `\b`-anchored regex matching in
   `catalog_taxonomy.py`, used by both `infer_meat_type` and `infer_dietary_flags`. This changed one
   real production behavior in the process: `"kozhi"` (chicken) no longer matches inside the
   concatenated Tamil compound `"Nattukozhi"` (word-boundary correctly rejects that too, since it's
   not a real standalone-word match) — fixed by adding `"nattukozhi"` as its own explicit keyword
   rather than relying on the accidental substring match. Regression tests cover the exact three
   examples from the review plus the compound-word case. Live re-run: `Gluten` tags dropped from 38
   to 15, `Nuts` from 15 to 8, `Milk-Dairy` from 10 to 8, `Sesame` from 6 to 3 — all removed false
   positives, spot-checked against the surviving `Gluten`-tagged dish list (all genuinely
   wheat/parotta/rava dishes) to confirm the fix didn't also strip real matches. `meat_type`
   distribution is unchanged (mutton 25 / fish 21 / chicken 18 / seafood 12 / other 6 / unresolved
   0) — the `nattukozhi` fix restored exact parity with the pre-fix numbers while now safely
   rejecting accidental matches elsewhere.

## MP-015 — Finish mapping master catalogue to application taxonomy

**Schema check done first, per the brief's explicit instruction.** Two real gaps found by
inspection, not assumed:

- **`dishes` had no meat/protein-type column.** Onboarding's meat-preference question (Chicken /
  Mutton / Fish / Seafood / Other) has nothing to write to — 0001 only had the binary
  `veg_or_nonveg`. Added via migration
  (`0016_dishes_meat_type_and_taxonomy_constraints.sql`): `meat_type text`, constrained to those 5
  values (or null), and constrained to only be set when `veg_or_nonveg = 'nonveg'`. **Caveat:** the
  mobile onboarding flow that would ask this question isn't built yet
  (`mobile/src/navigation/OnboardingNavigator.tsx` is still a placeholder, "MP-024 lands in a later
  phase") and no functional/technical spec doc exists in this repo to cross-check the exact
  wording against — the vocabulary is taken as given from the Phase 5 brief, not independently
  verified against a spec source.
- **The workbook has no prep-time column at all** — confirmed by reading its actual header row
  (`Dish ID, Meal Category, Diet, Dish Family, Subfamily / Parent, Specific Dish Variety, Tamil
  Name, Main Ingredient(s), Preparation Style, Region / Style, Common Pairing, Catalogue Note,
  Source URL`). "Preparation Style" is a cooking-method text field (e.g. "steamed", "deep-fried"),
  not a duration. **This is a genuine data-collection gap, not a mapping bug** — `prep_minutes`
  stays null for every workbook-sourced dish (553 of 573) and always will until that data is
  sourced separately. Only the 20 hand-authored dishes from `dev_placeholder_dishes.sql` have real
  values.

Mapping itself lives in `supabase/seed/catalog_taxonomy.py` (rules) and
`supabase/seed/ingest_catalog.py` (the pipeline that applies them — see MP-018 below, since the
"real ingestion pipeline" and "finish the taxonomy mapping" are the same piece of work run against
the same source). Every unmapped row is reported by name, not dropped or defaulted — see MP-018's
run report.

**Result, live on the Supabase project as of this phase:** all 573 dishes have `item_type`,
`veg_or_nonveg`, and `region_style` (already true before this phase); `track_variety` and
`meat_type`/`dietary_flags` (MP-017) are now populated for the 560 rows this phase's pipeline run
touched. `prep_minutes` remains null for 553 — the confirmed gap above, reported rather than
silently defaulted to some guess.

## MP-016 — Canonical ingredient list and aliases

`supabase/seed/ingredient_catalog.py`. Extends the ~30 ingredients `dev_placeholder_dishes.sql`
already seeded with 46 more (spices, millets, produce, proteins recurring across the workbook's
Main Ingredient(s) column) and adds 31 Tamil-English alias pairs (`vengaya`→onion, `kozhi`→chicken,
`meen`→fish, `muttai`→egg, etc.) — the same vocabulary `catalog_taxonomy.py`'s dietary-flag/meat-
type keyword matching uses, now on the canonical-identity side. `is_staple` tags every entry
explicitly (0001's meaning: excluded from grocery-photo matching).

**Not claimed exhaustive.** The workbook's Main Ingredient(s) column has ~390 distinct free-text
tokens; most of the long tail is single-occurrence, dish-specific phrasing that doesn't generalize
into a reusable canonical ingredient. This covers the recurring, genuinely reusable set — designed
to extend, not a one-time-complete ingredient ontology. `dish_ingredients` linking (connecting each
of the 573 dishes to its specific canonical ingredients) is **out of scope this phase** — the
workbook's Main Ingredient(s) text is free-form prose ("Dosa + minced mutton + egg"), not a
structured ingredient list, and parsing it into precise per-dish links reliably enough to trust
would need more than keyword matching. `dietary_flags` tagging (MP-017) reads that same free text
directly instead, which is what it actually needs.

Idempotent — `seed_ingredients()` upserts on `canonical_name` and `alias_text`, re-running is a
no-op for anything already seeded. AC ("aliases resolve to exactly one canonical ID") checked at
the data level: `backend/tests/test_ingredient_catalog.py::TestDataIntegrity` asserts every alias
target is a real canonical ingredient before any DB test runs.

## MP-017 — Dietary/allergen flag taxonomy

**Vocabulary is now decided** (Phase 5 brief §0): exactly `Nuts`, `Milk-Dairy`, `Gluten`, `Egg`,
`Seafood`, `Sesame` — matching the app's onboarding allergy question, casing included, so the same
string values work on both sides of `get_candidates`'s hard-exclusion array-overlap check with no
translation layer. This **supersedes** the broader draft in `docs/MP-017-dietary-flag-taxonomy.md`
(dairy/gluten/nuts/peanut/sesame/egg/soy/vegan/jain) — no vegan/jain (onboarding doesn't collect
them), peanut folded into `Nuts` (see below), soy dropped. Enforced at the DB level: `dishes`'s new
`dishes_dietary_flags_valid` constraint (0016) rejects any array containing a value outside this
list.

Tagging is automated, keyword-based, in `catalog_taxonomy.py::infer_dietary_flags` — matched
against Main Ingredient(s) + Subfamily + name text, combined. Every dish gets an explicit
evaluation (a real list, possibly empty, never left at an untouched default) — satisfies the AC
literally. Notable decisions, not just mechanical keyword lists:

- **Peanut is folded into `Nuts`.** Botanically a legume, not a tree nut, but the decided
  vocabulary has no separate peanut flag, and under-tagging a hard-exclusion allergen is the worse
  failure mode than over-tagging — peanut is one of the most common allergens in this cuisine
  (chutneys, tempering).
- **Coconut is deliberately NOT tagged as `Nuts` or `Milk-Dairy`.** Coconut allergy is real but
  distinct and rare; most tree-nut-allergic people tolerate coconut. Flagging it under either
  bucket would over-exclude across most of this cuisine's dishes for no real safety benefit.
- **`Seafood` covers both fish and shellfish** — the decided vocabulary has one bucket, not two.
- **`Parotta` dishes are always tagged `Gluten`**, even when the ingredient text doesn't spell out
  "wheat" (e.g. "Parotta + meat + salna") — the dish is inherently wheat-flour dough.
- **A dish's `Egg` tag isn't gated on the Diet column** — "Kari dosai" (Diet=Non-Vegetarian)
  contains egg in its ingredient text alongside mutton, and gets tagged `Egg` for that reason, not
  because Diet says so.

- **Keyword matching is word/phrase-boundary aware, not raw substring** (PR #12 review fix —
  see above) — a naive `in` check let `"til"` match inside `"lentil"`, `"egg"` inside
  `"eggplant"`, `"atta"` inside `"pattani"`, each a real false-positive risk this catalogue's text
  actually contains.

**Explicit limitation, stated plainly because this is safety-critical:** this is best-effort
tagging from the catalogue's own terse ingredient text (often 1–4 words), not a full recipe-level
ingredient audit. A dish whose real preparation includes a top-6 allergen but whose catalogue entry
doesn't mention it will be under-tagged. **Recommend a human spot-check pass on the 6 flags before
this gates real user exclusions in production**, the same caution MP-019 applies to regional
review. Live result (post review-fix): 79 of 573 dishes carry at least one flag (Seafood 33,
Gluten 15, Egg 13, Milk-Dairy 8, Nuts 8, Sesame 3).

**The same controlled vocabulary is now enforced on `user_profiles.dietary_restrictions` too**
(0017, PR #12 review fix) — see the review-round section above. Without this, a profile's exclusion
list could silently drift out of sync with the dish-side casing and never actually exclude anything.

## MP-018 — Catalog ingestion/validation pipeline

`supabase/seed/ingest_catalog.py`. **Not `load_master_catalogue.py` retrofitted** — a new,
re-runnable pipeline. What makes it idempotent:

- A unique index on `lower(dishes.name)` (0016) backs a real `ON CONFLICT ... DO UPDATE` upsert,
  replacing the old script's application-side "already exists?" pre-query.
- On conflict, `item_type`/`veg_or_nonveg`/`region_style`/`meat_type`/`dietary_flags` are refreshed
  from the workbook every run (it's the source of truth for those). `prep_minutes` is **never**
  touched on conflict — the workbook has no prep-time data at all. `track_variety` is corrected
  **one-directionally** (PR #12 review fix — see above): an existing `true` is overwritten only when
  the systematic rule computes `false` for that item_type (fixing a row that was only ever left at
  the unset schema default); an existing `false` is always preserved (it can only exist because
  something deliberately set it, e.g. `dev_placeholder_dishes.sql`'s non-rice/curd staple
  exceptions). Verified directly:
  `test_ingest_catalog.py::test_a_re_run_corrects_track_variety_left_at_the_unset_schema_default`
  and `::test_a_re_run_preserves_a_deliberately_curated_false_track_variety`.
- **Idempotency is asserted, not just claimed** — `test_running_the_same_workbook_twice_creates_no_duplicates`
  runs the pipeline twice against a real throwaway Postgres database and checks the row count and
  insert/update counts both times, per the brief's explicit AC.

**Found the hard way, fixed, worth recording:** the first real run against all 690 workbook rows
over Supabase's pooled connection dropped mid-transaction
(`server closed the connection unexpectedly`) with a naive single-transaction design. Fixed by
committing every 50 rows instead of one ~700-row transaction — safe specifically because the
upsert is idempotent, so a dropped connection just needs a re-run; already-committed rows update in
place as no-ops. `main()`'s failure message reports exactly how many rows were committed before the
drop, not a blanket "rolled back, nothing changed" (which would be inaccurate once batching is
involved).

**Live run report** (`python ingest_catalog.py <workbook>`, most recently re-run after the PR #12
review fixes above): 690 rows read, 130 skipped as condiment-only families (unchanged from the
original bulk load's own exclusion list), 560 mapped, 0 inserted / 560 updated (all 560 already
existed from the original bulk load — this run's job was filling in and correcting the taxonomy
fields, not adding new dishes). 2 rows landed on the low-confidence generic-meat fallback
(`Kari kothu parotta`, `Kari vadai` — both genuinely ambiguous "meat" or "kari" in the source text
with no more specific protein word anywhere in the row) and are called out by name in the run
output for review; 0 rows were fully unresolvable.

## MP-019 — Review Tamil Nadu-only coverage

**Human task, not automated** — `supabase/seed/mp019_review_candidates.py` produces a checklist
only; it never deletes or modifies a row. Two checks, run against the real workbook:

1. **Near-duplicate names** (7 groups) — dishes in the same `item_type` whose name collapses to
   the same text after stripping regional/style qualifiers ("Chettinad", "Kongunadu", "Tamil
   style", etc.). Likely mostly **legitimate regional variants, not real duplicates** — e.g.
   `Chettinad kozhi kuzhambu` / `Kongunadu kozhi kuzhambu` are different recipes from different
   regions, both valid catalogue entries. Flagged because the heuristic can't tell a real duplicate
   from a real variant; that judgment is explicitly Pratheep's:
   - [Kuzhambu] Chettinad kozhi kuzhambu / Kongunadu kozhi kuzhambu
   - [Kuzhambu] Chettinad meen kuzhambu / Meen kuzhambu
   - [Kuzhambu] Chettinad muttai kuzhambu / Muttai kuzhambu
   - [Kuzhambu] Chettinad mutton kuzhambu / Kongunadu mutton kuzhambu / Mutton kuzhambu Tamil style
   - [Rice dish] Chettinad chicken biryani / Kongunadu chicken biryani
   - [Rice dish] Dindigul vegetable biryani / Vegetable biryani Tamil style
   - [Chutney] Kongunadu kollu chutney / Kollu chutney (condiment-family — not imported as a
     standalone dish either way, listed for completeness)
2. **Non-Tamil-Nadu-specific sourcing** (77 rows) — per MP-003's regional gate ("reject anything
   only generically South Indian"), checked against the workbook's own Source URL column, not
   assumed from the dish names. `find_non_tamil_specific_sourced` (PR #12 review fix — renamed and
   broadened from `find_generic_sourced`, which only matched the literal phrase "south-indian" and
   silently skipped rows with no URL at all) flags a row if its source is missing/blank *or*
   present but doesn't mention Tamil Nadu — re-run against the real workbook, the result is
   unchanged: 0 rows have a missing URL, and the same 77 rows have a non-Tamil-mentioning one.
   **All 77 are non-veg/egg dishes citing the same single URL**
   (`archanaskitchen.com/.../delicious-south-indian-non-vegetarian-recipes-chicken-mutton-fish`) —
   effectively the entire non-veg portion of the catalogue traces to one generically-titled
   collection page rather than a Tamil-Nadu-specific source. **This reads as a citation-specificity
   gap, not evidence the dishes themselves aren't Tamil Nadu cuisine** — the dish names are
   overwhelmingly Tamil-coded (Chettinad/Kongunadu/Madurai/Dindigul prefixes, Tamil terms like
   kozhi/meen/muttai/eral/nandu) — but it's exactly the kind of sourcing gap MP-003's regional gate
   exists to catch, and is Pratheep's call: accept the citation as-is, find better per-dish
   sourcing, or treat as a data-quality item to revisit later. Full 77-row list is reproducible via
   `python supabase/seed/mp019_review_candidates.py <workbook>` — not duplicated here.

**No dishes were removed this phase.** Both lists above are inputs to a decision, not a decision.

## MP-020 — Validate slot/combo coverage (the hard gate)

`supabase/seed/validate_coverage.py`, run live against the catalog after MP-015/017/018 above.
Checks every `(item_type, veg_or_nonveg)` combination the schema defines, unfiltered and under
**every combination of simultaneous `dietary_flags` exclusions** a user could select (PR #12
review fix — the original version only checked one flag excluded at a time; see the review-round
section above for why that misses real gaps). 16 groups, each checked against every non-empty
subset of the 6-flag vocabulary (up to 63 subsets, computed in memory from one fetch per group —
not one query per subset), reporting only the *minimal* failing combinations. **MP-034's actual
combo templates don't exist yet** (that's exactly what this gate is supposed to unblock), so this
validates at the finest grain checkable right now; re-run once those templates land to check the
real per-slot requirements, not just this item_type × diet × flag-combination cross product.

**Result: gate FAILS. 4 zero-candidate gaps, reported rather than rounded away:**

| Combination | Candidates |
|---|---|
| `tiffin` / nonveg, excluding **Egg + Gluten together** | 0 |
| `kootu` / nonveg (unfiltered) | 0 |
| `curd` / nonveg (unfiltered) | 0 |
| `sweet` / nonveg (unfiltered) | 0 |

Plus one low-margin warning (non-zero, not a gate failure, but thin): `curd` / veg has only 1
candidate (Curd Rice) unfiltered.

**The first gap is new** — invisible to the original single-flag-only check, since `tiffin` /
nonveg passes both "excluding Egg alone" and "excluding Gluten alone" individually. A real user
with both an egg allergy and a gluten intolerance selecting `Egg` and `Gluten` together in
`dietary_restrictions` would have zero non-veg tiffin candidates. This needs the same kind of
decision as the other three: source more non-veg tiffin dishes free of both allergens from the
wider 690-row pool, or accept the gap for now.

**The other 3 gaps most likely reflect real Tamil Nadu culinary convention, not a sourcing
shortfall** — kootu, curd (rice), and sweets are vegetarian dish categories in this cuisine; a
genuinely non-veg version of any of them would be unusual, and the 690-row source catalogue doesn't
have one for any of the three. Two ways to close this, both Pratheep's call per the brief:

1. **Confirm these combinations should simply never be requested** — if MP-034's combo templates
   never ask for "non-veg kootu"/"non-veg curd"/"non-veg sweet" in the first place (plausible, given
   the cuisine), this isn't a real gap and the check can be scoped to drop nonsensical combinations
   rather than flag them.
2. **If a non-veg variant is genuinely wanted for one of these**, it needs sourcing beyond this
   690-row catalogue — nothing in the existing pool can fill it.

Not resolved either way in this phase — reported, per the brief's explicit instruction not to
silently work around a real finding.

## Definition of done — status

- All 573 dishes have complete taxonomy **except `prep_minutes`** (553/573 null — confirmed
  workbook gap, not silently defaulted).
- MP-017's 6 flags are explicitly evaluated (present or absent) on every dish, with word-boundary
  matching (PR #12 review fix) — done, with the stated best-effort/human-review caveat above. The
  same controlled vocabulary is now also enforced on `user_profiles.dietary_restrictions` (0017),
  closing the case-sensitivity gap the review round found.
- MP-018's ingestion is idempotency-tested against a real database, not just asserted, and now
  also correctly backfills `track_variety` for pre-existing rows rather than only new ones — done.
- MP-020's coverage report now checks simultaneous multi-flag exclusions, not just one at a time,
  and found 4 real gaps (one only visible because of that fix) — reported above, not silently
  accepted, decision pending.
