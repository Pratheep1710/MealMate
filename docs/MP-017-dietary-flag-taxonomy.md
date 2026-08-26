# MP-017 — Dietary/Allergen Flag Taxonomy: Proposal (Needs Your Confirmation)

**Superseded — see `docs/MP-015-020-catalog-pipeline.md`'s MP-017 section.** The Phase 5 brief
decided the vocabulary directly (`Nuts`, `Milk-Dairy`, `Gluten`, `Egg`, `Seafood`, `Sesame` —
narrower than the draft below: no vegan/jain/peanut/soy as separate flags, peanut folded into
`Nuts`, `Seafood` added), and it's now implemented and live. Left below as-is for the historical
record of the original proposal and its reasoning.

**Status: proposed, not implemented.** Per the Phase 2 brief §0, this is safety-critical — the
list below becomes the hard-exclusion set MP-043 uses to reject dishes outright, so it's presented
for confirmation rather than assumed. It is also blocked on the same dish workbook as the rest of
Track 1 (`docs/MP-015-catalog-blocked.md`): nothing below is wired into dish data yet, and won't be
until you confirm it and MP-018 has real catalog rows to tag.

## What's already decided (not part of this proposal)

- `dishes.veg_or_nonveg` is a separate existing column (0001 migration) — vegetarian/non-veg is
  **not** a `dietary_flags` value; it's handled by that column already.
- The functional/technical spec source documents (`version1_mealPlanner_functionalities.md`,
  `version1_mealPlanner_technical.md`) referenced elsewhere in `docs/` were not available in this
  session, so the onboarding question's exact restriction list (functional spec §2) couldn't be
  read directly. The candidate list below is derived only from the schema
  (`dishes.dietary_flags text[]`, `user_profiles.dietary_restrictions text[]`) and general
  South Indian home-cooking allergen/diet categories — flagged here explicitly as something to
  cross-check against the actual spec question list, not to be taken as equivalent to it.

## Proposed candidate list

Two categories, because they behave differently at exclusion time:

### Allergens (medical hard-exclusion — presence of the flag on a dish always excludes it for a
### user who has that restriction)

| Flag | Rationale |
|---|---|
| `dairy` | Ghee, curd, paneer are load-bearing in Tamil Nadu cooking (tempering, kootu, sweets) — common exclusion. |
| `gluten` | Wheat-based tiffin items (some parottas/upma varieties) vs. rice-based ones. |
| `nuts` | Cashew/almond are common in gravies and sweets. |
| `peanut` | Distinct from tree nuts (`nuts`) — common in South Indian chutneys/poriyal tempering; a peanut-allergic user isn't necessarily tree-nut allergic and vice versa, so kept separate. |
| `sesame` | Til/gingelly oil and seeds are common in tempering and some sweets — an allergen the "generic Indian food" assumption easily misses. |
| `egg` | Distinct from `veg_or_nonveg` — some "veg" combo templates might still not apply, but egg dishes exist per MP-003's catalog breakdown (12 egg dishes in the source pool) and need their own flag since not every egg-avoider is otherwise restricting meat. |
| `soy` | Less central to Tamil Nadu cooking than the above but common enough in packaged/processed ingredients to include. |

### Diet-type restrictions (ethical/religious — exclusion logic may be broader than a single ingredient tag)

| Flag | Rationale |
|---|---|
| `vegan` | Broader than `dairy` exclusion alone (also excludes honey, ghee) — proposed as its own flag rather than inferred from `dairy`, so MP-018's tagging doesn't have to get vegan-ness right by implication. |
| `jain` | Excludes onion/garlic/root vegetables in addition to being vegetarian — a meaningfully different exclusion shape than an allergen (whole-ingredient-category, not single-ingredient), worth a reviewer's explicit sign-off since it's the one flag that isn't a simple ingredient-presence check. |

## Open questions for you to confirm or correct

1. Is this the right list, or does the functional spec's actual onboarding question (§2) specify a
   different/shorter/longer set? If you have that spec available, the real list should come from
   there, not this proposal.
2. Should `jain`'s onion/garlic/root-vegetable exclusion be modeled as its own `dietary_flags`
   value on affected dishes (e.g., tag every dish containing onion/garlic/root veg with `jain`),
   or does it need a different mechanism (e.g., a per-ingredient `excludes_jain` property joined at
   query time)? The former fits the existing `text[]` column with no schema change; the latter is
   more precise but is new schema work not currently scoped anywhere.
3. Any flags to drop, or regional Tamil Nadu allergens/restrictions this list is missing?

## What happens once confirmed

- MP-018's ingestion script tags each imported dish's `dietary_flags` from this controlled list —
  values outside it get rejected/reported as invalid data, not silently accepted (matching MP-015's
  own AC).
- `backend/app/repositories/catalog.py`'s `get_candidates(..., exclude_dietary_flags=[...])` is
  already written and tested against this array-overlap exclusion mechanism (see
  `backend/tests/test_repositories.py::TestCatalogRepository::test_get_candidates_hard_excludes_dietary_flags`)
  — no code change needed once the vocabulary is settled, only real data.
