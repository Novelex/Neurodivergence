"""The query path — plain code, one branch (plus the live-search fallback). Working spec §7, §8.

scope_guard -> [translator -> retrieve -> live_search (if thin) -> rerank -> rank ->
writer -> citation_checker] -> terminal_state.

Live search replaces relying on a pre-built corpus (query/live_search.py) — decided
because that corpus isn't affordable at the current budget. retrieve() checks what's
already known first (cheap — one embedding call); live_search only runs, and only spends
real classify/audit budget, when the existing corpus doesn't have enough to work with.
This is a real trade against §4's determinism guarantee, accepted deliberately for a
single-developer prototype at this budget — see live_search.py's docstring for the honest
accounting of what that costs.

Six terminal_state values (§8): answered, refused, out_of_scope, no_evidence, split,
distress. This module is the state machine — no agent here decides what runs next.

Construct disambiguation (§7.4) is not wired in — it only fires when the SQL join
surfaces claims with divergent measure_ids, and claim extraction (agent 3) was never run
in this small-scale proof, so the claims table is empty and the check has nothing to
trigger on. That's an honest gap for this scope, not a bug.

Distress path (§9.2) is not implemented here either — scope guard classifies it
correctly, but the resource-table/follow-up-prompt response is real safety-content work
that deserves its own pass, not a stub bolted onto this proof.
"""

import re
from dataclasses import dataclass, field

from neurodiversity.agents import citation_checker, reranker, scope_guard, translator, writer
from neurodiversity.query import live_search, ranking, retrieval

MIN_CANDIDATES_FOR_ANSWER = 1
# Below this many candidates from the existing corpus, trigger a live search rather than
# declaring no_evidence outright — the whole point of live_search is that "we don't have
# it yet" should mean "go find it," not "give up," given there's no pre-built corpus to
# fall back on.
THIN_COVERAGE_THRESHOLD = 3


@dataclass
class TurnResult:
    terminal_state: str
    reflection: str | None = None
    prose: str | None = None
    citations: list = field(default_factory=list)
    evidence: dict | None = None  # counts only, never a probability — see api/schemas.py's EvidenceSummary
    debug: dict = field(default_factory=dict)


def handle_turn(raw_input: str) -> TurnResult:
    scope = scope_guard.classify(raw_input)
    classification = scope.output.classification.value
    print(f"[scope_guard] {classification}")

    if classification == "diagnostic_ask":
        return TurnResult(terminal_state="refused")
    if classification == "distress":
        return TurnResult(terminal_state="distress")
    if classification == "out_of_domain":
        return TurnResult(terminal_state="out_of_scope")

    trans = translator.translate(raw_input)
    research_query = trans.output.research_query
    reflection = trans.output.reflection
    print(f"[translator] research_query={research_query!r}")

    candidates = retrieval.retrieve(research_query, match_count=20)
    distinct_papers = {c.paper_id for c in candidates}
    print(f"[retrieve] {len(candidates)} candidates from {len(distinct_papers)} distinct papers in existing corpus")

    live_contexts = {}
    if len(distinct_papers) < THIN_COVERAGE_THRESHOLD:
        # Coverage is measured in distinct papers, not chunk count — 20 chunks from 2
        # papers is still thin. A synthesis answer drawn from too few sources is exactly
        # what tempts the writer to pad a claim with real-but-uncited specifics instead
        # of citing another paper for it, so trigger live search on paper diversity.
        # Phase A only here — cheap, no GPT-4o call. Everything found gets fetched,
        # chunked, and embedded; nothing gets classified or audited yet.
        live_contexts = live_search.ingest_cheap_for_query(research_query)
        print(f"[live_search] cheaply ingested {len(live_contexts)} papers (not yet classified/audited)")
        if live_contexts:
            candidates = retrieval.retrieve(research_query, match_count=20)
            distinct_papers = {c.paper_id for c in candidates}
            print(f"[retrieve] {len(candidates)} candidates from {len(distinct_papers)} distinct papers after live search")

    if len(candidates) < MIN_CANDIDATES_FOR_ANSWER:
        return TurnResult(terminal_state="no_evidence", reflection=reflection)

    rerank_input = [{"chunk_id": c.chunk_id, "text": c.text} for c in candidates]
    reranked = reranker.rerank(research_query, rerank_input)
    ranked_ids_by_relevance = reranked.output.ranked_chunk_ids
    print(f"[rerank] reordered {len(ranked_ids_by_relevance)} chunk_ids")

    candidates_by_id = {c.chunk_id: c for c in candidates}
    unique_paper_ids = {candidates_by_id[cid].paper_id for cid in ranked_ids_by_relevance if cid in candidates_by_id}

    # Phase B — the expensive part — only now, only for papers that actually survived
    # into the reranked set. A paper live_search fetched but that never surfaced here
    # never gets classified or audited, and never costs that money (§5.8's logic,
    # applied synchronously instead of via a background worker).
    if live_contexts:
        live_search.audit_surviving_papers(unique_paper_ids, live_contexts)

    paper_ranks = ranking.rank(list(unique_paper_ids))
    paper_rank_order = {row["paper_id"]: i for i, row in enumerate(paper_ranks)}
    print(f"[rank] {len(paper_ranks)} papers ranked")

    ranked_chunks = sorted(
        (candidates_by_id[cid] for cid in ranked_ids_by_relevance if cid in candidates_by_id),
        key=lambda c: paper_rank_order.get(c.paper_id, len(paper_rank_order)),
    )
    writer_input = [
        {"chunk_id": c.chunk_id, "paper_id": c.paper_id, "text": c.text} for c in ranked_chunks
    ]

    draft = writer.write(research_query, writer_input)
    prose = draft.output.prose
    citations = draft.output.citations
    print(f"[writer] {len(citations)} citations")

    def _render_prose(ordered_citations: list) -> str:
        """Build the displayed answer text directly from verified citations rather than
        trusting the writer's separately-generated `prose` field. Real testing showed
        `prose` and `citations[].sentence` are two independent outputs of the same model
        call that don't reliably agree byte-for-byte — string-matching between them (to
        drop a flagged sentence, or even just to check its [N] marker) kept leaving
        orphaned, unverified bracket markers in the shown answer. Constructing the text
        purely from citations makes that structurally impossible: every bracket shown is
        exactly the citation_number of a citation that's actually in the list."""
        sentences = []
        for c in ordered_citations:
            s = re.sub(r"\s*\[\d+\]\.?\s*$", "", c.sentence.strip()).rstrip()
            if not s.endswith((".", "!", "?")):
                s += "."
            sentences.append(f"{s} [{c.citation_number}]")
        return " ".join(sentences)

    def _build_answered(verified_citations: list) -> TurnResult:
        prose_text = _render_prose(verified_citations)
        cited_paper_ids = {q.paper_id for c in verified_citations for q in c.supporting_quotes}
        site_counts = [
            row["site_count"] for row in paper_ranks
            if row["paper_id"] in cited_paper_ids and row["site_count"] is not None
        ]
        evidence = {
            "independent_papers_cited": len(cited_paper_ids),
            "max_site_count": max(site_counts) if site_counts else None,
        }
        print(f"[evidence] {evidence}")
        return TurnResult(
            terminal_state="answered",
            reflection=reflection,
            prose=prose_text,
            citations=verified_citations,
            evidence=evidence,
            debug={"research_query": research_query},
        )

    supplied_chunks = [{"chunk_id": c.chunk_id, "text": c.text} for c in ranked_chunks]
    for attempt in range(2):  # one retry, capped (§2.5)
        mechanical_flags = citation_checker.check_mechanical(citations, supplied_chunks)
        flagged_numbers = {f.citation_number for f in mechanical_flags}
        verified = [c for c in citations if c.citation_number not in flagged_numbers]
        semantic_flags = citation_checker.check_semantic(verified) if verified else []

        all_flags = mechanical_flags + semantic_flags
        print(f"[citation_checker] attempt {attempt + 1}: {len(all_flags)} flags")
        for f in all_flags:
            print(f"    FLAGGED: {f.reason}")
            print(f"      sentence: {f.sentence[:200]!r}")
            print(f"      quote:    {f.quote[:200]!r}")
        if not all_flags:
            return _build_answered(citations)

        if attempt == 0:
            # Pass the actual flags in — the retry must know what was wrong to fix it,
            # not just re-roll the same call blindly (§7.6; this was the real bug behind
            # 3 flags becoming 5 on the previous, unguided retry).
            flag_pairs = [(f.sentence, f.quote, f.reason) for f in all_flags]
            draft = writer.write(research_query, writer_input, previous_flags=flag_pairs)
            prose = draft.output.prose
            citations = draft.output.citations
        else:
            # Final attempt still has flags. Real testing (both a dense-anatomy query and
            # an unrelated one) showed the writer reliably reintroduces one uncited-but-
            # true specific per regeneration, regardless of retry or temperature — a model
            # tendency further retries don't fix. Rather than discard an otherwise-verified
            # answer over one bad sentence, salvage: drop only the still-flagged sentences
            # (and their citations) and answer with what survived verification intact.
            # Falls back to no_evidence only if literally nothing survives.
            flagged_final_numbers = {f.citation_number for f in all_flags}
            salvaged_citations = [c for c in citations if c.citation_number not in flagged_final_numbers]
            if not salvaged_citations:
                return TurnResult(terminal_state="no_evidence", reflection=reflection)
            print(f"[salvage] dropped {len(flagged_final_numbers)} flagged citation(s), kept {len(salvaged_citations)}")
            return _build_answered(salvaged_citations)

    return TurnResult(terminal_state="no_evidence", reflection=reflection)
