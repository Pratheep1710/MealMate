"""MP-029: job entrypoints — the functions Render's scheduler (or a manual invocation) calls.

Scaffolding only in this phase: each entrypoint does the idempotent claim/upsert and
correlation-scoped logging around a pipeline step, and stops there. The actual weekly-generation
algorithm (M4, MP-034+) and the OpenAI call (MP-040, next phase per the Phase 2 brief) plug into
this shell rather than building their own job bookkeeping.
"""
