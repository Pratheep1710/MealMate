"""MP-029: FastAPI application entrypoint.

Phase 9 (MP-092/093/094) adds the first product routes — see app/routes.py — now that onboarding
completion needs to trigger real generation and render an instant fallback synchronously, neither
of which the scheduled-script-only architecture could do. This is also the first thing that makes
Render's health check (below) load-bearing rather than decorative: app/main.py must actually be
deployed and served for these to be reachable at all — see the repo-root render.yaml.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.config import ConfigError, load_config
from app.routes import router

app = FastAPI(title="Meal Planner backend")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        load_config()
    except ConfigError:
        return {"status": "degraded", "reason": "configuration invalid"}
    return {"status": "ok"}
