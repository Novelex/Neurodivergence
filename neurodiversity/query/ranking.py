"""Deterministic SQL rank. No model call. Working spec §7.3.

Real implementation is in supabase/query_functions.sql's rank_papers function, not here —
the ranking itself must be a query, not in-memory Python logic, so it stays unit-testable
and explainable line by line, per §7.3. This module just calls it.

has_meta and cohorts from the working spec's illustrative order-by clause are not
implemented — no schema column captures either yet (see the SQL file's comment). Ranking
here uses site_count, fields_absent_ratio, and n_total only. Publication year and journal
are never inputs to this function, by design (§7.3).

fields_absent_ratio counts 'unchecked' as 'absent' (§5.8, §7.3) — a paper still waiting on
Phase B's audit must not rank as if it had cleared every check just because nothing has
been examined yet. This is what makes the two-phase ingestion split (§5.8) safe.
"""

from neurodiversity.db.client import get_service_client


def rank(paper_ids: list[str]) -> list[dict]:
    """Returns paper_ids in ranked order, each with the fields the rank was computed from."""
    if not paper_ids:
        return []
    db = get_service_client()
    resp = db.rpc("rank_papers", {"paper_ids": paper_ids}).execute()
    return resp.data
