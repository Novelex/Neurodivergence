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

Nine terminal_state values (§8's original six, plus practical_support, greeting, and
needs_clarification): answered, refused, out_of_scope, no_evidence, split, distress,
practical_support, greeting, needs_clarification. This module is the state machine — no
agent here decides what runs next.

Construct disambiguation (§7.4) is not wired in — it only fires when the SQL join
surfaces claims with divergent measure_ids, and claim extraction (agent 3) was never run
in this small-scale proof, so the claims table is empty and the check has nothing to
trigger on. That's an honest gap for this scope, not a bug.

Distress path (§9.2) is not implemented here either — scope guard classifies it
correctly, but the resource-table/follow-up-prompt response is real safety-content work
that deserves its own pass, not a stub bolted onto this proof.
"""

import re
import time
from dataclasses import dataclass, field

from neurodiversity import community_accounts, console_log as log
from neurodiversity import practical_resources
from neurodiversity.agents import broadener, citation_checker, general_chat, greeter, reranker, scope_guard, translator, writer
from neurodiversity.query import evidence_grade, live_search, ranking, retrieval

MIN_CANDIDATES_FOR_ANSWER = 1
# Below this many candidates from the existing corpus, trigger a live search rather than
# declaring no_evidence outright — the whole point of live_search is that "we don't have
# it yet" should mean "go find it," not "give up," given there's no pre-built corpus to
# fall back on.
THIN_COVERAGE_THRESHOLD = 3
# Paper-count alone isn't sufficient: real testing found a query where 8 distinct papers
# already sat in the (small, leftover-from-other-topics) local corpus, all just loosely
# ADHD-adjacent rather than actually on-topic, so coverage looked fine by count while the
# writer had nothing genuinely relevant to cite and produced a technically-verified but
# substantively off-target answer. There's no labeled relevance data to calibrate this
# against (same honest gap as every other uncalibrated threshold in this system), so this
# is a starting heuristic, not a tuned value — and 0.5 was itself shown to be too low by
# real testing: "cost-effectiveness of ADHD treatment options" scored 0.523 (barely over
# 0.5), skipped live search, and produced an answer built from generically ADHD-adjacent
# papers (treatment-access shortages, symptom variability) that never actually addressed
# cost-effectiveness — only 1 of the 8 "distinct" papers had anything the writer could
# genuinely use. Raised to 0.6 on that evidence; still a heuristic, not a tuned value, and
# should keep being revisited as more real query traffic exists to check it against.
THIN_SIMILARITY_THRESHOLD = 0.6
# Genuinely zero relevant literature is rare — the more common failure is a research_query
# specific enough that retrieval and live search don't surface what does exist on the
# wider topic. Rather than declare no_evidence the first time coverage looks thin, widen
# the query up to this many times (agents/broadener.py), retrying retrieval + live search
# each time, before actually giving up. Capped, not unbounded — same §2.5 "loop on facts,
# not judgement" principle as the citation-checker retry: this widens the SEARCH honestly
# each time, it never lets the writer answer from citations that don't verify.
MAX_BROADEN_ATTEMPTS = 2

@dataclass
class TurnResult:
    terminal_state: str
    reflection: str | None = None
    prose: str | None = None
    citations: list = field(default_factory=list)
    evidence: dict | None = None  # counts only, never a probability — see api/schemas.py's EvidenceSummary
    resources: list = field(default_factory=list)  # practical_support only — static table, never model output
    community_corroboration: dict | None = None  # no_evidence only — static table, never model output (§9.1)
    clarification_options: list = field(default_factory=list)  # needs_clarification only
    debug: dict = field(default_factory=dict)


def handle_turn(raw_input: str, context_summary: str = "", recent_turns: list[tuple[str, str]] | None = None) -> TurnResult:
    """context_summary/recent_turns: short-term session memory (agents/summarizer.py) —
    always already-scrubbed research_query/reflection text from earlier turns in this
    same session, never raw_input, current or past. The caller (api/routes/sessions.py)
    owns fetching this from the database; this module stays decoupled from the sessions/
    turns tables, matching how every other piece of state here is passed in, not looked up."""
    log.turn_start(raw_input)
    started = time.monotonic()
    result = _handle_turn(raw_input, context_summary, recent_turns or [])
    log.turn_end(result.terminal_state, time.monotonic() - started)
    return result


def _handle_turn(raw_input: str, context_summary: str, recent_turns: list[tuple[str, str]]) -> TurnResult:
    scope = scope_guard.classify(raw_input)
    classification = scope.output.classification.value
    log.stage("scope_guard", classification)

    if classification == "diagnostic_ask":
        return TurnResult(terminal_state="refused")
    if classification == "distress":
        return TurnResult(terminal_state="distress")
    if classification == "practical_support":
        topic = scope.output.practical_topic.value if scope.output.practical_topic else None
        log.sub(f"practical_topic={topic!r}")
        return TurnResult(terminal_state="practical_support", resources=practical_resources.for_topic(topic))
    if classification == "greeting":
        reply = greeter.greet()
        return TurnResult(terminal_state="greeting", prose=reply.output.message)
    if classification == "out_of_domain":
        chat = general_chat.reply(raw_input)
        return TurnResult(terminal_state="out_of_scope", prose=chat.output.message)

    trans = translator.translate(raw_input, context_summary, recent_turns)
    if trans.output.needs_clarification:
        log.stage("translator", "needs_clarification", style="cyan")
        return TurnResult(
            terminal_state="needs_clarification",
            prose=trans.output.clarifying_question,
            clarification_options=trans.output.clarification_options,
        )
    research_query = trans.output.research_query
    reflection = trans.output.reflection
    log.stage("translator", f"research_query={research_query!r}")

    def _no_evidence() -> TurnResult:
        # Checks research_query, never raw_input — §7.2's privacy boundary means nothing
        # downstream of the translator ever sees raw_input, and this is no exception.
        corroboration = community_accounts.for_query(research_query)
        if corroboration:
            log.sub("community corroboration matched (§9.1)", style="cyan")
        return TurnResult(
            terminal_state="no_evidence",
            reflection=reflection,
            community_corroboration=corroboration,
            debug={"research_query": research_query},
        )

    live_contexts = {}
    for broaden_attempt in range(MAX_BROADEN_ATTEMPTS + 1):
        candidates = retrieval.retrieve(research_query, match_count=20)
        distinct_papers = {c.paper_id for c in candidates}
        top_similarity = max((c.similarity for c in candidates), default=0.0)
        log.stage("retrieve", f"{len(candidates)} candidates from {len(distinct_papers)} distinct papers (top similarity {top_similarity:.3f})", style="blue")

        is_thin = len(distinct_papers) < THIN_COVERAGE_THRESHOLD
        is_low_relevance = top_similarity < THIN_SIMILARITY_THRESHOLD
        if is_thin or is_low_relevance:
            # Coverage is measured in distinct papers AND relevance, not chunk count alone
            # — 20 chunks from 2 papers is still thin, but so is 8 papers that are merely
            # loosely on-topic rather than actually relevant to this specific question. A
            # synthesis answer drawn from too few or too-tangential sources is exactly what
            # tempts the writer to pad a claim with real-but-uncited specifics, or to answer
            # from whatever's nearest instead of what's actually relevant — so trigger live
            # search on either signal, not just paper count.
            # Phase A only here — cheap, no GPT-4o call. Everything found gets fetched,
            # chunked, and embedded; nothing gets classified or audited yet.
            log.stage("live_search", f"triggering: thin={is_thin}, low_relevance={is_low_relevance}", style="magenta")
            live_contexts = live_search.ingest_cheap_for_query(research_query)
            log.sub(f"cheaply ingested {len(live_contexts)} papers (not yet classified/audited)")
            if live_contexts:
                candidates = retrieval.retrieve(research_query, match_count=20)
                distinct_papers = {c.paper_id for c in candidates}
                top_similarity = max((c.similarity for c in candidates), default=0.0)
                log.stage("retrieve", f"{len(candidates)} candidates from {len(distinct_papers)} distinct papers after live search (top similarity {top_similarity:.3f})", style="blue")
                is_thin = len(distinct_papers) < THIN_COVERAGE_THRESHOLD
                is_low_relevance = top_similarity < THIN_SIMILARITY_THRESHOLD

        if not is_thin and not is_low_relevance:
            break  # good coverage — proceed with this research_query as-is

        if broaden_attempt == MAX_BROADEN_ATTEMPTS:
            break  # widened as far as the cap allows — proceed with whatever this found;
            # the len(candidates) check right below is what actually falls back honestly

        widened = broadener.broaden(research_query)
        log.stage("broaden", f"{research_query!r} -> {widened.output.broadened_query!r}", style="magenta")
        research_query = widened.output.broadened_query
        live_contexts = {}  # discard the narrower query's live-search results; not relevant to the new one

    if len(candidates) < MIN_CANDIDATES_FOR_ANSWER:
        return _no_evidence()

    rerank_input = [{"chunk_id": c.chunk_id, "text": c.text} for c in candidates]
    reranked = reranker.rerank(research_query, rerank_input)
    ranked_ids_by_relevance = reranked.output.ranked_chunk_ids
    log.stage("rerank", f"reordered {len(ranked_ids_by_relevance)} chunk_ids", style="blue")

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
    log.stage("rank", f"{len(paper_ranks)} papers ranked", style="blue")

    ranked_chunks = sorted(
        (candidates_by_id[cid] for cid in ranked_ids_by_relevance if cid in candidates_by_id),
        key=lambda c: paper_rank_order.get(c.paper_id, len(paper_rank_order)),
    )
    writer_input = [
        {"chunk_id": c.chunk_id, "paper_id": c.paper_id, "text": c.text} for c in ranked_chunks
    ]

    draft = writer.write(research_query, writer_input)
    opening = draft.output.opening
    prose = draft.output.prose
    citations = draft.output.citations
    log.stage("writer", f"{len(citations)} citations", style="green")

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
        if not verified_citations:
            # A writer draft with zero citations trivially has zero flags to check, so
            # without this guard it would fall straight through as "answered" with empty
            # prose and an empty citations list — an answer that looks like success but
            # has nothing in it, which is worse than declining outright.
            log.warn("writer produced zero citations — no_evidence, not an empty answered")
            return _no_evidence()
        prose_text = f"{opening.strip()} {_render_prose(verified_citations)}" if opening.strip() else _render_prose(verified_citations)
        cited_paper_ids = {q.paper_id for c in verified_citations for q in c.supporting_quotes}
        site_counts = [
            row["site_count"] for row in paper_ranks
            if row["paper_id"] in cited_paper_ids and row["site_count"] is not None
        ]
        grade_result = evidence_grade.compute(cited_paper_ids, paper_ranks)
        evidence = {
            "independent_papers_cited": len(cited_paper_ids),
            "max_site_count": max(site_counts) if site_counts else None,
            "evidence_grade": grade_result["grade"],
            "evidence_grade_factors": grade_result["factors"],
        }
        log.success(f"evidence: {evidence}")
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
        log.stage(
            "citation_checker",
            f"attempt {attempt + 1}: {len(all_flags)} flags",
            style="yellow" if all_flags else "green",
        )
        for f in all_flags:
            log.flag(f.reason, f.sentence, f.quote)
        if not all_flags:
            return _build_answered(citations)

        if attempt == 0:
            # Pass the actual flags in — the retry must know what was wrong to fix it,
            # not just re-roll the same call blindly (§7.6; this was the real bug behind
            # 3 flags becoming 5 on the previous, unguided retry).
            flag_pairs = [(f.sentence, f.quote, f.reason) for f in all_flags]
            draft = writer.write(research_query, writer_input, previous_flags=flag_pairs)
            opening = draft.output.opening
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
                return _no_evidence()
            log.warn(f"salvage: dropped {len(flagged_final_numbers)} flagged citation(s), kept {len(salvaged_citations)}")
            return _build_answered(salvaged_citations)

    return _no_evidence()
