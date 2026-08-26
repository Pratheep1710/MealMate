# MP-015–020 (Catalog track) — Blocked Pending the Dish Workbook

**Superseded — see `docs/MP-015-020-catalog-pipeline.md`.** The workbook this doc describes as
missing was found on disk in Phase 5 (it was never committed to the repo, by design — see that
doc), and MP-015 through MP-020 are now done. Left below as-is for the historical record of what
was checked and why at the time.

**Status: not started this phase.** Per the Phase 2 brief §0: "MP-015 is blocked pending the dish
catalog workbook... Confirm it's finished and in hand before starting MP-015. If it isn't, work
Tracks 2 and 3 first."

## What was checked

- The repository (all branches, including the unmerged `feature/phase-1-foundation` Phase 1
  branch) — no dish data file anywhere in the tree.
- The uploads attached to this task — no workbook present.
- GitHub code search across this repo for `Tamil_Nadu_Dishes_Master_Catalogue` (the filename named
  in `docs/MP-003-catalog-target-decision.md` as the source) — zero results.

`docs/MP-003-catalog-target-decision.md` describes this workbook in detail (690 raw entries: 596
veg, 82 nonveg, 12 egg; a "Master Dishes" sheet; `Dish Family`/`Subfamily`/`Source URL`/`Region /
Style` columns) — so its existence and shape are documented, but the file itself was not available
to work from in this session.

## What this blocks

Per the brief's own dependency graph (§1), MP-015 blocks the rest of Track 1 in sequence:

| Task | Depends on | Status |
|---|---|---|
| MP-015 (taxonomy mapping) | dish workbook | **Blocked** |
| MP-016 (canonical ingredients) | MP-015 | Blocked (transitively) |
| MP-017 (dietary flag taxonomy) | MP-015 | Blocked on wiring — but see `docs/MP-017-dietary-flag-taxonomy.md`, which proposes and seeks confirmation of the controlled vocabulary now, independent of the workbook, so that decision isn't also sitting idle |
| MP-018 (ingestion script) | MP-015, MP-016, MP-017 | Blocked |
| MP-019 (Tamil Nadu review) | MP-018 | Blocked |
| MP-020 (coverage validation) | MP-019 | Blocked |

MP-020's coverage report is the hard gate the brief calls out before generation-engine work (M4,
MP-034+) can safely start — that gate cannot be reached this phase.

## What was done instead

Per the brief's explicit instruction, Tracks 2 (mobile shell, MP-022/023) and 3 (backend skeleton,
MP-029–031) were built this phase since neither depends on catalog data. The backend's catalog
repository (`backend/app/repositories/catalog.py`) is written and tested against synthetic rows
inserted directly in tests — it's ready to serve real data the moment MP-018's ingestion job lands,
but currently has nothing to read from a live catalog table.

## Unblocking

Once the workbook is available (as a repo file, an attached upload, or a location this session/a
follow-up session can read), MP-015 can start immediately — MP-003's decision doc already specifies
the ~200-dish curation target and the source column mapping to work from.
