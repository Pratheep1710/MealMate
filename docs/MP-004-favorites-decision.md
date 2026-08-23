# MP-004 — Favorites Onboarding Behavior: Decision Record

**Decision: onboarding seed plus explicit manual favorites — not automatic over-time accrual.**

Review fix (PR #1): the original wording of this decision ("onboarding-only acquisition, no
built up over time path") directly contradicted its own rationale section, which described users
marking a dish as a favorite during edits after onboarding — that *is* an over-time path. The
decision itself was never wrong; the label for it was. Retitled and reworded below so the two
paths this actually has are named accurately instead of one being asserted away.

## The two acquisition paths, both in v1

1. **Onboarding seed** — functional spec §2 Q8, optional/skippable, collected once at signup.
2. **Explicit manual favorite** — functional spec §6's edit-time flow: a user marks a dish as a
   favorite while editing a slot. Available at any time after onboarding, not gated by anything.

**What is *not* in v1**: automatic, system-driven promotion of a dish to favorite status based on
behavior (e.g. "you picked this 4 times, want to favorite it?"). That would need a signal source —
the accept/skip weight from functional spec §4 item 5 — and MP-002 deferred accept/skip to v2. So
there is no *inferred* favoriting in v1, only the two *explicit* paths above.

## Rationale
- Functional spec §2 Q8 already collects favorites at onboarding.
- Functional spec §6 already describes marking a favorite during a normal edit — this was always
  in scope; MP-004 only had to decide whether anything *beyond* these two explicit paths was
  needed for v1.
- Automatic accrual has no signal source without accept/skip (MP-002, deferred), so it's excluded
  for a structural reason, not a preference — there's nothing to drive it yet.

## What this means for downstream tasks
- `MP-008` (`user_favorite_dishes` schema) needs no acquisition-source or timestamp column — every
  row is a plain insert, whether it came from the onboarding seed or an edit-time action; the
  schema doesn't need to distinguish which path created it.
- No dedicated "favorites suggestions" UI surface in v1 mobile scope (that would be the automatic
  path, which is excluded).
- Cap stays the existing 5–8 estimate (functional spec §6, technical spec §7), unchanged by this
  decision — tune once real usage data exists, per the technical spec's own note.

## Revisit trigger
MP-002 (accept/skip) shipping in a later version — at that point, re-open whether favorites should
also accrue automatically from sustained accept signals, on top of the two explicit paths above.
