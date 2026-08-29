"""Phase 1 — prove the whole pipeline works end to end, on a tiny scale.

Not the full ~500-per-condition corpus (§5.1.1). For a handful of real papers per
condition, across all five conditions: fetch from PubMed -> full text from PMC ->
chunk + embed -> store in Supabase -> run the design classifier for real -> run the
correct auditor for real, routed by design_type -> print what actually landed in the
database. Idempotent — safe to re-run.

Shared processing logic lives in neurodiversity/ingestion/process_paper.py — the live
query-time search (query/live_search.py) uses the exact same function, not a copy.

Usage: uv run python scripts/phase1_e2e_test.py
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from neurodiversity.db.client import get_service_client
from neurodiversity.ingestion.process_paper import process_paper
from neurodiversity.ingestion.sources import pubmed

RETMAX_PER_CONDITION = 5


def main() -> None:
    db = get_service_client()
    all_results = []

    for condition in pubmed.CONDITION_CLAUSES:
        print(f"\n=== {condition} (retmax={RETMAX_PER_CONDITION}) ===")
        pmids = pubmed.esearch(condition, retmax=RETMAX_PER_CONDITION)
        print(f"esearch -> {len(pmids)} PMIDs: {pmids}")
        papers = pubmed.efetch(pmids)

        for paper in papers:
            try:
                result = process_paper(db, paper)
                all_results.append((condition, *result))
            except Exception as exc:
                print(f"      !! failed, skipping: {exc}")
                all_results.append((condition, paper.pubmed_id, paper.title, "ERROR", None))

    print("\n=== Phase 1 summary (all conditions) ===")
    for condition, pmid, title, design_type, audited in all_results:
        audit_note = f" (audited: {audited})" if audited else ""
        print(f"  [{condition}] {pmid}: {design_type}{audit_note} — {title[:55]}")

    by_design = {}
    for _, _, _, design_type, _ in all_results:
        by_design[design_type] = by_design.get(design_type, 0) + 1
    print("\nDesign type distribution:", by_design)


if __name__ == "__main__":
    main()
