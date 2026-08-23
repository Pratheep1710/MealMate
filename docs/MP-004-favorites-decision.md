# MP-004 — Favorites Onboarding Behavior: Decision Record

**Decision: Onboarding-only acquisition in v1.** No "built up over time" path.

## Rationale
- Functional spec §2 Q8 already collects favorites at onboarding (optional, skippable). The only open
  question (functional spec §8) was whether an "over time" path is added on top.
- The natural over-time mechanism would be the accept/skip signal (functional spec §4 item 5) — and
  MP-002 deferred that to v2. With no accept/skip weight to promote a frequently-picked dish to
  favorite status automatically, "built up over time" has no signal source to build from in v1.
- Manual promotion (editing a slot and marking it a favorite, per functional spec §6) already exists
  as an implicit "over time" path through normal edit-time interaction — no separate mechanism needed.

## What this means for downstream tasks
- `MP-008` (`user_favorite_dishes` schema) needs no additional acquisition-timestamp or
  source-tracking column — rows are written either at onboarding seed or via explicit edit-time
  "mark as favorite," both a simple insert.
- No dedicated "favorites suggestions" UI surface in v1 mobile scope.
- Cap stays the existing 5–8 estimate (functional spec §6, technical spec §7), unchanged by this
  decision — tune once real usage data exists, per the technical spec's own note.

## Revisit trigger
MP-002 (accept/skip) shipping in a later version — at that point, re-open whether favorites should
also accrue from sustained accept signals.
