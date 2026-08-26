# MP-034–047 — Phase 6 Weekly Generation Engine

## Status

Implemented on `codex/phase-6-implementation`.

### Task-by-task status

| Task | Status | Implementation |
|---|---|---|
| MP-034 | Complete | Candidate catalog and generation context |
| MP-035 | Complete | Rolling 10-day variety exclusion with favorites exemption |
| MP-036 | Complete | Weekly dates, prep bias, non-veg targets, and combo templates |
| MP-037 | Complete | Strict Pydantic `WeeklyMenu` structured-output contract |
| MP-038 | Complete | Deterministic shared static prompt prefix |
| MP-039 | Complete | Compact per-user dynamic prompt suffix |
| MP-040 | Complete | OpenAI Responses API adapter with structured parsing |
| MP-041–044 | Complete | Six code-level validation rules and one corrective retry |
| MP-047 | Complete | Deterministic fallback with explicit relaxation ordering |
| Provider-quality eval harness | **Open** | Unit/integration tests cover contracts, but a representative model-output eval dataset and quality/cost regression gate have not been built yet. This remains required before changing the production model or prompt behavior. |

Phase 6 closes the generation loop that Phase 3 scaffolded and Phase 5's catalog unlocked:

1. Claim `(user_id, week_start)` atomically before any provider call.
2. Build a stable slot-filtered catalog prefix plus a compact per-user suffix.
3. Request a Pydantic-structured `WeeklyMenu` through the OpenAI Responses API.
4. Validate the six frozen business rules.
5. Retry once with concise validation feedback.
6. Fall back deterministically after two provider/validation failures.
7. Replace only the targeted plan dates, freeze the grocery snapshot, enqueue `week_ready`, and
   mark the job done in one database transaction.

The OpenAI adapter follows the current official Structured Outputs example:
`client.responses.parse(..., text_format=WeeklyMenu)` and reads `response.output_parsed`.
Source: https://developers.openai.com/api/docs/guides/structured-outputs

## Model choice

The selected Phase 6 baseline is **`gpt-5.6-luna`**, supplied through `OPENAI_MODEL` (not
hard-coded). This weekly menu task is constrained to a curated catalog, returns a strict schema,
and is protected by six deterministic validators plus a safe fallback, so the cost-sensitive,
high-volume member of the current GPT-5.6 family is the appropriate starting point. Official
OpenAI guidance describes Luna as the cost-sensitive/high-volume option and lists the current
models as available through the Responses API:
https://developers.openai.com/api/docs/models

This is a baseline choice, not an assertion that quality has already been benchmarked. The
repository secret must be set to the selected model, and any model/prompt change must wait for the
open eval harness above and be compared on representative weekly-menu cases. Official model
guidance likewise recommends validating resource savings only when the workload's evals still
pass: https://developers.openai.com/api/docs/guides/latest-model

## Runtime modules

- `app/services/generation_context.py` — shared catalog loading plus profile, dates, favorites,
  history, Reserves eligibility, and deterministic count-only non-veg placement. The scheduler
  loads the catalog once per sweep and injects it into every per-profile context.
- `app/services/generation_eligibility.py` — the shared fail-closed dietary and Reserves hard gate
  used by both response validation and fallback selection.
- `app/services/generation_prompt.py` — static-first JSON prompt. User restrictions, dinner style,
  history, and availability appear only in the dynamic suffix; tests pin this cache invariant.
- `app/services/openai_generation.py` — injectable Responses API boundary. Tests never call the
  network, and provider exception messages are not copied into logs/prompts.
- `app/services/menu_validation.py` — candidate membership, in-week variety, trailing-10-day
  exclusion, combo templates, dietary safety, and non-veg quota/pattern.
- `app/services/rule_based_fallback.py` — favorites first, then least-recently-used, weekday prep
  bias, history relaxation before any softer constraint, and `needs_manual_pick` when no safe
  candidate exists. Dietary restrictions and Reserves eligibility are never relaxed.
- `app/services/plan_persistence.py` — target-date replacement, quantity-aware grocery aggregation,
  Reserves top-up filtering, frozen snapshot, and `week_ready` outbox row.
- `app/services/generation_engine.py` — two-attempt lifecycle, fallback, job status/attempt tracking,
  atomic scheduled-failure retry, rollback-on-write-failure, and explicit remaining-week
  regeneration.
- `scripts/run_weekly_generation.py` / `.github/workflows/weekly-generation.yml` — daily 8 PM IST
  sweep using the existing planning-mode trigger direction, followed by week-ready push delivery.

## Run locally

```powershell
cd backend
.venv/Scripts/python.exe scripts/run_weekly_generation.py
```

The same `SUPABASE_*`, `OPENAI_*`, and optional `EXPO_ACCESS_TOKEN` variables documented in
`backend/.env.example` are required. A live provider call is intentionally not part of the test
suite; use the workflow's manual dispatch for controlled end-to-end verification before relying on
the schedule.

## Verification

- Pure tests cover prompt ordering/caching, all six validation rules, provider parsing/failures,
  retry feedback, deterministic fallback, grocery aggregation, and orchestration failure recovery.
- Real-Postgres tests (run in CI) cover Reserves ingredient eligibility, history/recency queries,
  partial-week replacement, quantities, job restart, profile sweep, plan persistence, snapshot, and
  notification outbox behavior against the actual migrations.
- Full backend test, Ruff, strict mypy, and dependency audit are the PR gates.

## Catalog data limitations carried forward

- Phase 5 populated catalog taxonomy and a canonical ingredient vocabulary, but did not populate
  each dish's `dish_ingredients` links. The Reserves eligibility and grocery rollup are complete and
  tested, but live output will remain sparse until those links (and quantities where known) are
  loaded.
- The MP-020 report's Egg+Gluten/non-veg-tiffin gap remains useful catalog coverage signal. Phase 6
  interprets the frozen quota rule at the **date** level (a target date needs at least one non-veg
  dish), rather than requiring every slot on that date to be non-veg. Dietary conflicts are still
  hard rejects and an actually empty safe item-type pool still becomes `needs_manual_pick`.
