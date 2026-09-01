"""FastAPI app entrypoint. Working spec §12.1.

Swagger/OpenAPI docs at /docs, generated from the same Pydantic models (api/schemas.py)
that validate the requests and responses — not a separately maintained spec.

Run with: uv run uvicorn neurodiversity.api.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from neurodiversity.api.routes import papers, sessions
from neurodiversity.api.schemas import HealthResponse
from neurodiversity.config import settings
from neurodiversity.db.client import get_service_client

app = FastAPI(title="NeuroEvidence")
# Every API route lives under /api — not for clean-URL reasons, but because Vercel's
# Python serverless runtime doesn't reliably pass the pre-rewrite original path through
# to the ASGI app the way a plain unprefixed catch-all rewrite assumes (confirmed by real
# deployment testing: /health 404'd with FastAPI's own "Not Found" shape, meaning the
# request reached the app but matched no route). Prefixing here, not just in vercel.json,
# keeps local dev and Vercel identical — one behavior, not an environment-specific split.
app.include_router(sessions.router, prefix="/api")
app.include_router(papers.router, prefix="/api")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    keys_configured = {
        "ncbi_api_key": bool(settings.ncbi_api_key),
        "openalex_api_key": bool(settings.openalex_api_key),
        "semantic_api_key": bool(settings.semantic_api_key),
        "crossref_contact_email": bool(settings.crossref_contact_email),
        "openai_api_key": bool(settings.openai_api_key),
        "supabase_url": bool(settings.supabase_url),
        "supabase_anon_key": bool(settings.supabase_anon_key),
        "supabase_service_role_key": bool(settings.supabase_service_role_key),
    }

    try:
        get_service_client().table("papers").select("id").limit(1).execute()
        db_reachable = True
    except Exception:
        db_reachable = False

    return HealthResponse(api_keys_configured=keys_configured, database_reachable=db_reachable)


# Mounted last so it never shadows an API route above — anything not matched by /api/*
# falls through to the static frontend (static/index.html).
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[2] / "static", html=True), name="static")
