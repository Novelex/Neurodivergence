"""Semantic Scholar Graph API. Working spec §5.1.

Two independent jobs in this module:

get_citations(): citation-graph lookups, offline ingestion only, never at query time —
runs alongside OpenAlex's citation-graph coverage (referenced_works/cited_by_api_url), not
as a replacement for it. Semantic Scholar's citation graph and influence classification
are independently sourced from OpenAlex's, so cross-referencing the two catches gaps
either one misses on its own, rather than trusting a single citation-graph provider.

search_papers(): live, per-question paper DISCOVERY — a second, independently-indexed
source alongside PubMed for query/live_search.py's live search, not a replacement for it.
Added after real testing showed Semantic Scholar's index surfaces genuinely relevant
papers PubMed's search missed for the exact same query (different indexing/ranking, wider
venue coverage — conference proceedings, preprints, non-PubMed-indexed journals). Only
results carrying a PubMed ID in externalIds are used: this system's whole ingestion
pipeline (papers.pubmed_id unique, upsert on_conflict="pubmed_id" throughout
process_paper.py) is built around PMID as the dedup key, so a Semantic-Scholar-only result
with no PMID has no home in this schema yet — that's a real, current limitation, not
silently worked around here. Uses SEMANTIC_API_KEY (docs/setup.md).
"""

import httpx

from neurodiversity.config import settings
from neurodiversity.db.models import Paper

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


def search_papers(query: str, limit: int = 8) -> list[Paper]:
    """Live discovery search — query/live_search.py's second source alongside
    pubmed.esearch_free_text/efetch. Returns Paper objects in the exact same shape
    ingest_cheap() already expects, so no downstream code needs to know which source a
    paper came from. Silently drops any result with no PubMed ID (see module docstring)."""
    resp = httpx.get(
        f"{S2_BASE}/paper/search",
        params={
            "query": query,
            "limit": limit,
            "fields": "title,abstract,year,venue,externalIds",
        },
        headers=_headers(),
        timeout=30.0,
    )
    resp.raise_for_status()
    papers = []
    for record in resp.json().get("data", []):
        external_ids = record.get("externalIds") or {}
        pmid = external_ids.get("PubMed")
        if not pmid:
            continue
        papers.append(
            Paper(
                pubmed_id=pmid,
                pmc_id=external_ids.get("PubMedCentral"),
                doi=external_ids.get("DOI"),
                title=record.get("title") or "",
                abstract=record.get("abstract"),
                journal=record.get("venue"),
                publication_year=record.get("year"),
            )
        )
    return papers
