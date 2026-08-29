"""Semantic Scholar Graph API — citation graph. Working spec §5.1.

Runs alongside OpenAlex's citation-graph coverage (referenced_works/cited_by_api_url),
not as a replacement for it — both were considered mutually exclusive alternatives at
one point (OpenAlex was adopted after Semantic Scholar's API application was initially
rejected), but a key was obtained afterward and there's a real reason to keep both:
Semantic Scholar's citation graph and influence classification are independently
sourced from OpenAlex's, so cross-referencing the two catches gaps either one misses on
its own, rather than trusting a single citation-graph provider's coverage.

/graph/v1/paper/{paper_id}/citations, looked up via external PMID/DOI identifiers,
batched via /graph/v1/paper/batch where possible. Runs during offline ingestion only,
never at query time. Uses SEMANTIC_API_KEY (docs/setup.md).
"""

import httpx

from neurodiversity.config import settings

S2_BASE = "https://api.semanticscholar.org/graph/v1"


def _headers() -> dict:
    return {"x-api-key": settings.semantic_api_key} if settings.semantic_api_key else {}


def get_citations(pmid: str) -> list[dict]:
    """Papers citing this one, looked up via external PMID. Returns raw citation records."""
    resp = httpx.get(
        f"{S2_BASE}/paper/PMID:{pmid}/citations",
        params={"fields": "title,externalIds,year"},
        headers=_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])
