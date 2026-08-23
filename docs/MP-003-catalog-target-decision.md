# MP-003 — Initial Curated Dish Catalog Target: Decision Record

**Decision: ~200 dishes, within the specified 150–300 range.**

## Rationale
- Source master catalogue (`Tamil_Nadu_Dishes_Master_Catalogue_Claude.xlsx`, Master Dishes sheet) has
  690 raw entries: 596 vegetarian, 82 non-vegetarian, 12 egg, spanning all meal-slot categories
  (including 52 kootu, 40 sambar, 50 chutney variants). 200 is a curation target from that pool, not
  a hard cap — MP-020's coverage validation is the actual gate.
- Mid-range: large enough to give slot/item_type × veg/non-veg × dietary-restriction coverage margin
  for MP-020, without pushing MP-019's human-review pass (Tamil-Nadu-only check, duplicate removal)
  into a much heavier lift than 150 would require.
- Keeps the static LLM prompt prefix (technical spec §5) moderate — full catalog is sent unfiltered
  per-user for cache-friendliness, so catalog size directly sizes token cost per call.

## Completion / quality gates (feed into MP-018–020)
1. **Coverage gate (MP-020):** every (slot, item_type) combination required by the combo templates
   (technical spec §4/§5) must have a non-zero eligible candidate count for both veg and non-veg where
   applicable, and under at least the common `dietary_flags` exclusions (no dairy, no gluten, no nuts).
2. **Dedup gate (MP-018):** zero duplicate dishes after `ingredient_aliases`-style canonicalization —
   catalogue's own Overview sheet already claims dedup at 690, but the curated subset needs its own
   pass since selection may reintroduce near-duplicates across `Dish Family`/`Subfamily`.
3. **Regional gate (MP-019):** every selected dish traceable to a Tamil Nadu source per the catalogue's
   `Source URL` / `Region / Style` columns — reject anything only generically "South Indian."
4. **Staple/produce tagging complete:** every selected dish's ingredients resolve to a canonical
   `ingredient_id` with `is_staple` set (technical spec §4) before MP-018 ingestion.

## What this means for downstream tasks
- `MP-015` (taxonomy mapping) and `MP-016` (canonical ingredients) scope their selection work against
  this ~200 target, not the full 690-row master list.
- If MP-020's coverage report finds gaps at 200, the fallback is pulling more rows from the existing
  690-row master pool (already sourced/vetted), not new sourcing work — cheap to raise if needed.

## Revisit trigger
MP-020 coverage report surfaces a zero-candidate combination that can't be filled from the existing
690-row master pool.
