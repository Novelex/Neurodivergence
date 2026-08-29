"""FastAPI app entrypoint. Working spec §12.1.

Swagger/OpenAPI docs at /docs, generated from the same Pydantic models (api/schemas.py)
that validate the requests and responses — not a separately maintained spec.

Run with: uv run uvicorn neurodiversity.api.main:app --reload
"""

from fastapi import FastAPI

from neurodiversity.api.routes import papers, sessions
from neurodiversity.api.schemas import HealthResponse
from neurodiversity.config import settings
from neurodiversity.db.client import get_service_client

app = FastAPI(title="NeuroEvidence")
app.include_router(sessions.router)
app.include_router(papers.router)


@app.get("/health", response_model=HealthResponse)
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
