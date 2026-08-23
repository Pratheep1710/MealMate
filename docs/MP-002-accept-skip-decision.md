# MP-002 — Accept/Skip Preference Weighting: Decision Record

**Decision: Deferred to v2. Not in v1 scope.**

## Rationale
- Functional spec §4 item 5 and §7 explicitly flag this as the first candidate to cut if scope needs
  tightening, and §7 non-goals lists it as "cut first if scope needs to tighten."
- Removing it drops one full mechanism from Phase 1: a per-slot accept/skip UI, a weight column, and
  a read-time ranking adjustment in the generation candidate query — none of which are needed for the
  three highest-value productivity features (grocery list, quick swap, regenerate-week).
- No downstream v1 task requires it. Favorites (MP-004) doesn't depend on it once favorites are
  onboarding-only (see MP-004 decision record).

## What this means for downstream tasks
- `MP-007` (dish/ingredient schema) and `MP-015` (catalog taxonomy mapping) need no weight column.
- Generation candidate filtering (M4) uses no accept/skip signal in v1.
- No dedicated accept/skip UI in M3/M5 mobile scope.

## Revisit trigger
First real usage data suggesting onboarding-only personalization isn't enough, or an explicit product
decision to invest in it post-v1.
