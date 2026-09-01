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
#
# Deliberately defensive: StaticFiles(directory=...) raises RuntimeError at import time
# if the directory doesn't exist, which would crash the entire app object's construction
# — every route, including /api/health, would then fail identically, which is exactly
# what real Vercel deployment testing showed (both / and /api/health returned the same
# byte-identical FastAPI 404, the signature of the app never finishing import rather than
# a routing mismatch). If Vercel's `includeFiles` bundling doesn't preserve this exact
# path, the API still comes up; only the static frontend is missing, which is at least
# diagnosable instead of masquerading as "every route not found."
_static_dir = Path(__file__).resolve().parents[2] / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
else:
    print(f"[main] WARNING: static directory not found at {_static_dir} — frontend will not be served, but /api/* routes are unaffected")
