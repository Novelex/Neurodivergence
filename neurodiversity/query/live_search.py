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

from concurrent.futures import ThreadPoolExecutor, as_completed

from neurodiversity import console_log as log
from neurodiversity.db.client import get_service_client
from neurodiversity.ingestion.process_paper import IngestResult, classify_and_audit, ingest_cheap
from neurodiversity.ingestion.sources import pubmed

MAX_LIVE_RESULTS = 8
# Real testing found turns taking far longer than expected — traced to this module
# processing up to MAX_LIVE_RESULTS papers strictly one at a time, each a real network
# fetch (PMC) plus OpenAI call(s), pure sequential I/O wait. Papers are fully independent
# (separate DB rows keyed by pubmed_id/paper_id, no shared mutable state across
# iterations), so running them concurrently is safe and changes nothing about the
# result — same papers, same writes, just not waited on one at a time. Capped, not
# unbounded, to stay polite to PMC/OpenAI rate limits rather than firing 8 requests at
# once with no ceiling.
MAX_CONCURRENT_PAPERS = 4


def ingest_cheap_for_query(research_query: str, max_results: int = MAX_LIVE_RESULTS) -> dict[str, IngestResult]:
    """Phase A only — no GPT-4o call. Returns paper_id -> IngestResult for later Phase B use."""
    db = get_service_client()
    pmids = pubmed.esearch_free_text(research_query, retmax=max_results)
    log.sub(f"{len(pmids)} PMIDs for {research_query!r}: {pmids}", style="magenta")
    if not pmids:
        return {}

    papers = pubmed.efetch(pmids)
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
