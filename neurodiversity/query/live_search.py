"""Live, per-question paper search — decided in place of a pre-built corpus.

A real pre-built, pre-audited corpus (§5.1's ~500-per-condition design) isn't affordable
at the current budget. Instead: when a question comes in, search PubMed directly for it,
cheaply ingest (fetch, chunk, embed — no GPT-4o call) everything found, let vector search
determine which of those papers are actually relevant, and only then spend the expensive
classify+audit calls (Phase B, §5.8) on that narrowed-down subset — not on every paper
the search happened to return. This is the same two-phase split the project already
committed to for the pre-built corpus, just triggered synchronously inside a live turn
instead of by a background worker.

This is a real trade against the original architecture, worth being honest about: §4's
determinism guarantee ("the same question produces the same answer on any run") doesn't
hold here the way it would against a fixed corpus, since PubMed's live results can shift
between runs, and this adds real latency to the turn (a live search + embed, not just a
lookup). Accepted deliberately given the budget — this is a single-developer prototype,
not a production system serving many people yet.

Already-known papers are never reprocessed (ingest_cheap's own pubmed_id check handles
that), so a repeated or related question mostly hits cache and costs little.
"""

from neurodiversity import console_log as log
from neurodiversity.db.client import get_service_client
from neurodiversity.ingestion.process_paper import IngestResult, classify_and_audit, ingest_cheap
from neurodiversity.ingestion.sources import pubmed

MAX_LIVE_RESULTS = 8


def ingest_cheap_for_query(research_query: str, max_results: int = MAX_LIVE_RESULTS) -> dict[str, IngestResult]:
    """Phase A only — no GPT-4o call. Returns paper_id -> IngestResult for later Phase B use."""
    db = get_service_client()
    pmids = pubmed.esearch_free_text(research_query, retmax=max_results)
    log.sub(f"{len(pmids)} PMIDs for {research_query!r}: {pmids}", style="magenta")
    if not pmids:
        return {}

    papers = pubmed.efetch(pmids)
    results = {}
    for paper in papers:
        try:
            ingest_result = ingest_cheap(db, paper)
            results[ingest_result.paper_id] = ingest_result
        except Exception as exc:
            log.warn(f"failed to ingest {paper.pubmed_id}: {exc}")
    return results


def audit_surviving_papers(paper_ids: set[str], contexts: dict[str, IngestResult]) -> None:
    """Phase B — call only for paper_ids that actually survived retrieval as relevant."""
    db = get_service_client()
    for paper_id in paper_ids:
        ctx = contexts.get(paper_id)
        if ctx is None:
            continue  # not one of ours (already existed before this search) — nothing to defer
        if ctx.already_processed:
            continue
        classify_and_audit(db, ctx)
