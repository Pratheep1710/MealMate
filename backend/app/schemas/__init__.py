"""MP-037: structured-output contracts for LLM calls.

Distinct from app.models (which mirrors the Postgres schema, field-for-field): these types
describe what the model is asked to return, not what's stored. They're the first validation gate
a raw model response passes through — structural only (types, required fields, enums) — before
app-layer business-rule validation (MP-041-044) runs.
"""
