# Meal Planner — v1 implementation

Tamil Nadu meal-planning app. Personal/family use v1, built to scale to multi-user without a schema
rework. See `docs/` for the functional/technical specs and the decision records this phase produced.

## Structure

```
docs/                Scope baseline + decision records (MP-001–005), Supabase setup guide
supabase/
  migrations/         SQL schema + RLS policies (MP-007–011, MP-013)
  tests/              pglite-backed schema + negative multi-tenant RLS tests (Node/vitest)
backend/
  app/config.py       Typed config, fails fast on missing/invalid env vars (MP-014)
  tests/              Config validation tests + Supabase Auth sign-in test (MP-012)
mobile/               Expo React Native app, TypeScript (MP-021)
```

## Running things

**Schema + RLS tests** (no live Supabase project needed — runs against real Postgres via pglite):
```bash
cd supabase/tests && npm install && npm test
```

**Backend config tests**:
```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest tests/ -v
```

**Mobile app**:
```bash
cd mobile
npm install
npm run web    # or: npm run android / npm run ios
npm test       # smoke test
```

## Current status

Foundation, mobile shell/live plan views, push notifications, the curated catalog pipeline, and
the Phase 6 weekly generation engine are implemented. See
`docs/MP-034-044-generation-engine.md` for the generation lifecycle, verification, and the
remaining per-dish ingredient-data limitation affecting live grocery/Reserves richness.
