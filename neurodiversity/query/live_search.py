"""Live, per-question paper search — decided in place of a pre-built corpus.

Nothing here is a pre-built, pre-audited corpus (§5.1's ~500-per-condition design isn't
affordable at the current budget, and was dropped for exactly that reason). When a
question comes in, this searches live sources directly for it, cheaply ingests (fetch,
chunk, embed — no GPT-4o call) everything found, lets vector search determine which of
those papers are actually relevant, and only then spends the expensive classify+audit
calls (Phase B, §5.8) on that narrowed-down subset — not on every paper the search
happened to return. This is the same two-phase split the project already committed to for
the (abandoned) pre-built corpus, just triggered synchronously inside a live turn instead
of by a background worker. query/retrieval.py's own vector search over already-ingested
chunks is a CACHE of prior live searches, not a separate static corpus — the same paper,
once fetched here, is never re-fetched (pubmed_id dedup below), so a repeated or related
question mostly hits that cache. It never substitutes for running a real search here.

Two independent sources, run concurrently, merged by pubmed_id before ingestion: PubMed
(pubmed.py) and Semantic Scholar (semantic_scholar.py). Added after real testing showed
Semantic Scholar's independently-indexed search surfaces genuinely relevant papers PubMed
missed for the identical query — wider venue coverage (conference proceedings, preprints,
journals PubMed doesn't index), different ranking. Semantic Scholar results with no PubMed
ID are dropped (see semantic_scholar.py's own docstring) — this system's whole schema is
built around pubmed_id as the dedup/upsert key.

This is a real trade against the original architecture, worth being honest about: §4's
determinism guarantee ("the same question produces the same answer on any run") doesn't
hold here the way it would against a fixed corpus, since live results can shift between
runs, and this adds real latency to the turn (two live searches + embed, not just a
lookup). Accepted deliberately given the budget — this is a single-developer prototype,
not a production system serving many people yet.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from neurodiversity import console_log as log
from neurodiversity.db.client import get_service_client
from neurodiversity.db.models import Paper
from neurodiversity.ingestion.process_paper import IngestResult, classify_and_audit, ingest_cheap
from neurodiversity.ingestion.sources import pubmed, semantic_scholar

MAX_LIVE_RESULTS = 8
# Real testing found turns taking far longer than expected — traced to this module
# processing up to MAX_LIVE_RESULTS papers strictly one at a time, each a real network
# fetch (PMC) plus OpenAI call(s), pure sequential I/O wait. Papers are fully independent
# (separate DB rows keyed by pubmed_id/paper_id, no shared mutable state across
# iterations), so running them concurrently is safe and changes nothing about the
# result — same papers, same writes, just not waited on one at a time. Raised from 4 to 8
# (== MAX_LIVE_RESULTS) so a full live search fetches all candidate papers in one batch
# instead of two — explicitly accepted, real risk: this is more concurrent load against
# PubMed/PMC and OpenAI's embedding endpoint per turn, higher chance of hitting a rate
# limit under real traffic than the more conservative 4 was.
MAX_CONCURRENT_PAPERS = 8


def _search_pubmed(research_query: str, max_results: int) -> list[Paper]:
    pmids = pubmed.esearch_free_text(research_query, retmax=max_results)
    log.sub(f"pubmed: {len(pmids)} PMIDs for {research_query!r}: {pmids}", style="magenta")
    return pubmed.efetch(pmids) if pmids else []


def _search_semantic_scholar(research_query: str, max_results: int) -> list[Paper]:
    try:
        papers = semantic_scholar.search_papers(research_query, limit=max_results)
    except Exception as exc:
        log.warn(f"semantic_scholar search failed: {exc}")
        return []
    log.sub(f"semantic_scholar: {len(papers)} papers with a PubMed ID for {research_query!r}", style="magenta")
    return papers


def ingest_cheap_for_query(research_query: str, max_results: int = MAX_LIVE_RESULTS) -> dict[str, IngestResult]:
    """Phase A only — no GPT-4o call. Returns paper_id -> IngestResult for later Phase B use."""
    db = get_service_client()

    # Two independent sources, run concurrently — neither waits on the other.
    with ThreadPoolExecutor(max_workers=2) as pool:
        pubmed_future = pool.submit(_search_pubmed, research_query, max_results)
        s2_future = pool.submit(_search_semantic_scholar, research_query, max_results)
        pubmed_papers = pubmed_future.result()
        s2_papers = s2_future.result()

    # Merged by pubmed_id — PubMed's own metadata wins on overlap (it's already
    # filtered through SHARED_FILTERS' quality gate; Semantic Scholar's copy of the same
    # paper isn't a second opinion worth keeping once we have PubMed's).
    papers_by_pmid: dict[str, Paper] = {p.pubmed_id: p for p in s2_papers if p.pubmed_id}
    papers_by_pmid.update({p.pubmed_id: p for p in pubmed_papers if p.pubmed_id})
    papers = list(papers_by_pmid.values())
    log.sub(f"{len(papers)} distinct papers across both sources", style="magenta")
    if not papers:
        return {}

    results = {}
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PAPERS) as pool:
        futures = {pool.submit(ingest_cheap, db, paper): paper for paper in papers}
        for future in as_completed(futures):
            paper = futures[future]
            try:
                ingest_result = future.result()
                results[ingest_result.paper_id] = ingest_result
            except Exception as exc:
                log.warn(f"failed to ingest {paper.pubmed_id}: {exc}")
    return results


def audit_surviving_papers(paper_ids: set[str], contexts: dict[str, IngestResult]) -> None:
    """Phase B — call only for paper_ids that actually survived retrieval as relevant."""
    db = get_service_client()
    to_audit = [
        contexts[pid] for pid in paper_ids
        if pid in contexts and not contexts[pid].already_processed
    ]
    if not to_audit:
        return
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PAPERS) as pool:
        futures = {pool.submit(classify_and_audit, db, ctx): ctx for ctx in to_audit}
        for future in as_completed(futures):
            ctx = futures[future]
            try:
                future.result()
            except Exception as exc:
                log.warn(f"failed to classify/audit {ctx.paper_id}: {exc}")
