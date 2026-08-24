"""MP-029: FastAPI application entrypoint.

No product routes yet — those land with the phases that need them (M4 generation triggers, M6
notification webhooks). This exists now so the package is importable/runnable as a FastAPI app
(the AC's "FastAPI package" half) and so Render has something to point a health check at.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import ConfigError, load_config

app = FastAPI(title="Meal Planner backend")


@app.get("/health")
def health() -> dict[str, str]:
    try:
        load_config()
    except ConfigError:
        return {"status": "degraded", "reason": "configuration invalid"}
    return {"status": "ok"}
