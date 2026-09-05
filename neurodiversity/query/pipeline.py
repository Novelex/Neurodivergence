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

Distress path (§9.2): agents/danger.py runs concurrently with scope_guard on every turn
(not a scope_guard category) and wins unconditionally over whatever scope_guard says —
static crisis resources (crisis_resources.py) plus a followup_prompt tailored to whether
the danger is to the person themselves or someone they're worried about. No lexical fast-
path (Layer 0) — see danger.py's own docstring for why that's a deliberate gap, not an
oversight. No session-level escalation/decay across turns and no dedicated retention
policy for a distress turn's raw_input beyond the standard purge schedule — both real,
open pieces of safety-content work, not silently assumed solved by what's here.
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from neurodiversity import community_accounts, console_log as log
from neurodiversity import crisis_resources, practical_resources
from neurodiversity.agents import broadener, citation_checker, danger, general_chat, greeter, reranker, router, scope_guard, translator, writer
from neurodiversity.config import settings
from neurodiversity.ingestion.embeddings import embed_chunk
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
# Lowered from 2 to 1 for latency, explicitly accepted trade: a worst-case turn now runs
# one fewer full live-search+retrieve cycle, but a question needing two full widenings to
# find real coverage will now fall back to no_evidence instead of finding it — this
# partially undoes the "literature is rarely silent" broadening fix for the sake of speed.
MAX_BROADEN_ATTEMPTS = 1
# See its use below (writer_input construction) for the full reasoning — caps the final,
# fully-ordered chunk list before it reaches the writer, purely for latency.
MAX_WRITER_CHUNKS = 10

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
    message: str | None = None  # practical_support: overrides the schema default (see below).
    # distress: the tailored followup_prompt text (differs for third_party_concern).
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
    # No text-match shortcut here on purpose — a keyword/exact-match fast path previously
    # lived here and was removed: greeting is a judgment call ("hy" vs "hydroxyzine dosing",
    # a greeting with a real question attached vs one without), and a plain-code match can
    # only ever approximate that. scope_guard's model call is the one place that judgment
    # is actually made, for every message, no exceptions carved out for speed.
    #
    # danger.py runs CONCURRENTLY with scope_guard, not after it — they're independent
    # questions ("is this dangerous" vs "what kind of message is this otherwise") that used
    # to be forced into one five-way classification, which was the actual root cause of a
    # real, documented bug (see danger.py's module docstring). Running them concurrently
    # means this costs no extra wall-clock time on the common case versus the old single
    # call, and a danger signal always wins regardless of what scope_guard says — nothing
    # downstream of danger.py's "none" needs it to be correct, but everything downstream of
    # a real signal needs it to never be skipped.
    # settings.use_router_agent (default False): route through the merged scope_guard+
    # translator+broadener agent instead — see agents/router.py's module docstring. Clean,
    # instant rollback: it's a config flag, not a code branch to revert.
    router_output = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        danger_future = pool.submit(danger.check, raw_input, context_summary, recent_turns)
        if settings.use_router_agent:
            classify_future = pool.submit(router.route, raw_input, context_summary, recent_turns)
        else:
            classify_future = pool.submit(scope_guard.classify, raw_input, context_summary, recent_turns)
        danger_result = danger_future.result()
        classify_result = classify_future.result()

    signal = danger_result.output.signal.value
    log.stage("danger", signal, style="magenta" if signal != "none" else "dim")
    classification = classify_result.output.classification.value
    practical_topic_enum = classify_result.output.practical_topic
    if settings.use_router_agent:
        router_output = classify_result.output
        log.stage("router", classification)
    else:
        scope = classify_result
        log.stage("scope_guard", classification)

    if signal != "none":
        if signal == "third_party_concern":
            followup = (
                "Would you like guidance on how to support them, or help with anything "
                "else in your message?"
            )
        else:
            followup = "Would you also like the question in your message answered?"
        return TurnResult(
            terminal_state="distress",
            resources=crisis_resources.RESOURCES,
            message=followup,
            debug={"danger_signal": signal},
        )
    if classification == "practical_support":
        topic = practical_topic_enum.value if practical_topic_enum else None
        log.sub(f"practical_topic={topic!r}")
        resources = practical_resources.for_topic(topic)
        # A practical need connected to a condition is NOT mutually exclusive with a real
        # research question about the same thing — real testing case: workplace
        # harassment/discrimination experienced by autistic/ADHD people is genuinely
        # studied (employment outcomes, disclosure, accommodations effectiveness), even
        # though "what does the law say" itself isn't literature-answerable. Rather than
        # route straight to organizations and never check, run the SAME research pipeline
        # underneath (matching §9.2's distress pattern: safety/practical content shown
        # unconditionally, the research angle attempted alongside it, never assumed away)
        # and attach whatever literature-backed answer it finds alongside the resources.
        # force_topic makes _run_research's translator step always produce a research_query
        # instead of ever bailing to needs_clarification — scope_guard already established
        # this message is connected to the domain (that's how it got here), so the only
        # open question is what to search for, not whether to search at all. Every
        # practical_support question goes through the exact same research pipeline as an
        # "answerable" one, no exceptions: there's no such thing as "too vague to search"
        # once the topic area is known, since the topic itself grounds the query.
        log.stage("practical_support", "also attempting research pipeline", style="cyan")
        if settings.use_router_agent:
            # The router already produced a research_query grounded in this topic in the
            # same call that classified it (its own prompt forbids needs_clarification for
            # practical_support) — no force_topic re-call needed, unlike the scope_guard
            # path below.
            research_result = _run_research_router(router_output)
        else:
            research_result = _run_research(raw_input, context_summary, recent_turns, force_topic=topic or "general")
        if research_result.terminal_state == "answered":
            return TurnResult(
                terminal_state="practical_support",
                reflection=research_result.reflection,
                prose=research_result.prose,
                citations=research_result.citations,
                evidence=research_result.evidence,
                resources=resources,
                debug=research_result.debug,
            )
        # A real search DID run (force_topic rules out needs_clarification here) and came
        # up empty after broadening — say so honestly, never that the literature "can't"
        # answer this outright, since that's a claim about this one search, not a
        # permanent verdict on the whole literature.
        message = (
            "Here are organizations that can help directly with this. A literature "
            "search was also run underneath and didn't surface a matching study "
            "this time — try asking the underlying question on its own and it may "
            "find something."
        )
        return TurnResult(terminal_state="practical_support", resources=resources, message=message)
    if classification == "greeting":
        reply = greeter.greet()
        return TurnResult(terminal_state="greeting", prose=reply.output.message)
    if classification == "out_of_domain":
        chat = general_chat.reply(raw_input, context_summary, recent_turns)
        # Persisted under the same "research_query" key the research path uses so
        # _get_session_context (api/routes/sessions.py) picks up chit-chat exchanges into
        # the same memory window — recent_turns was never meant to be research-only, that
        # was just the first path that needed it.
        return TurnResult(terminal_state="out_of_scope", prose=chat.output.message, debug={"research_query": chat.output.topic})

    # classification == "answerable"
    if settings.use_router_agent:
        return _run_research_router(router_output)
    return _run_research(raw_input, context_summary, recent_turns)


def _run_research(
    raw_input: str,
    context_summary: str,
    recent_turns: list[tuple[str, str]],
    force_topic: str | None = None,
) -> TurnResult:
    """translator -> _search_and_write. Called for "answerable" classifications directly,
    and ALSO for "practical_support" ones (see above) so a practical need connected to a
    condition still gets checked against the literature, not routed past it. Only used
    when settings.use_router_agent is False — see _run_research_router for the merged-
    agent equivalent, and _search_and_write for the shared chain both delegate to.

    force_topic: only set by the practical_support caller — forwarded to
    translator.translate so it never bails to needs_clarification on this path (see the
    call site's comment)."""
    trans = translator.translate(raw_input, context_summary, recent_turns, force_topic=force_topic)
    if trans.output.needs_clarification:
        log.stage("translator", "needs_clarification", style="cyan")
        return TurnResult(
            terminal_state="needs_clarification",
            prose=trans.output.clarifying_question,
            clarification_options=trans.output.clarification_options,
        )
    log.stage("translator", f"research_query={trans.output.research_query!r}")
    return _search_and_write(trans.output.research_query, trans.output.reflection)


def _run_research_router(route_output) -> TurnResult:
    """Router equivalent of _run_research — the router (agents/router.py) already did
    translator's job in the same call that classified the message, so this skips straight
    to the shared chain using its research_query/reflection/alt_query. Only reachable when
    settings.use_router_agent is True.

    Defensive fallback: the router's own prompt instructs it to never set
    needs_clarification for practical_support, but if it does anyway (a model not
    following instructions is always possible), this still returns needs_clarification
    honestly rather than forcing a query that was never actually formed — the caller
    (practical_support branch) already handles a non-"answered" result by falling back to
    resources-only, same as the old path's behavior when translator couldn't form a query."""
    if route_output.needs_clarification:
        log.stage("router", "needs_clarification", style="cyan")
        return TurnResult(
            terminal_state="needs_clarification",
            prose=route_output.clarifying_question,
            clarification_options=route_output.clarification_options,
        )
    log.stage("router", f"research_query={route_output.research_query!r}")
    return _search_and_write(route_output.research_query, route_output.reflection, alt_query=route_output.alt_query or None)


def _search_and_write(research_query: str, reflection: str, alt_query: str | None = None) -> TurnResult:
    """The shared retrieve -> live_search -> broaden -> rerank -> rank -> writer ->
    citation_checker chain — everything past "a research_query and reflection exist,"
    regardless of which agent produced them. alt_query: a pre-computed widened query (from
    agents/router.py) — when given, the broaden step uses it directly instead of calling
    agents/broadener.py, since the router already did that work in its one call."""

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
        # Computed once per iteration, reused for both retrieve() calls below — they run
        # against the SAME research_query within one iteration (only a new broaden_attempt
        # changes it), so re-embedding a second time was a real, avoidable extra OpenAI
        # round-trip on every iteration where live_search fires (the common case).
        query_embedding = embed_chunk(research_query)
        candidates = retrieval.retrieve(research_query, match_count=20, query_embedding=query_embedding)
        distinct_papers = {c.paper_id for c in candidates}
        top_similarity = max((c.similarity for c in candidates), default=0.0)
        log.stage("retrieve", f"{len(candidates)} candidates from {len(distinct_papers)} distinct papers (top similarity {top_similarity:.3f})", style="blue")

        is_thin = len(distinct_papers) < THIN_COVERAGE_THRESHOLD
        is_low_relevance = top_similarity < THIN_SIMILARITY_THRESHOLD
        # Live search only on the FIRST pass, not after broadening — measured, repeated
        # evidence (scripts/measure_pipeline_timing.py, every practical_support run
        # tested) showed the second live search, on the broadened query, finding zero new
        # papers every single time: broadening one step out rarely changes what PubMed/
        # Semantic Scholar's keyword index actually has, so re-querying both live sources
        # again was consistently 4-10s of pure waste. The broadened query still gets a
        # fresh vector retrieve() against whatever the FIRST live search already added —
        # this only skips searching PubMed/Semantic Scholar a second time in the same
        # turn, it doesn't skip using what the first search found.
        if (is_thin or is_low_relevance) and broaden_attempt == 0:
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
                # Same query_embedding as above — research_query hasn't changed, only the
                # corpus underneath it has (new papers just got ingested).
                candidates = retrieval.retrieve(research_query, match_count=20, query_embedding=query_embedding)
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

        if alt_query:
            widened_query = alt_query
            log.stage("broaden", f"{research_query!r} -> {widened_query!r} (router-provided, no extra call)", style="magenta")
        else:
            widened = broadener.broaden(research_query)
            widened_query = widened.output.broadened_query
            log.stage("broaden", f"{research_query!r} -> {widened_query!r}", style="magenta")
        research_query = widened_query
        live_contexts = {}  # discard the narrower query's live-search results; not relevant to the new one

    if len(candidates) < MIN_CANDIDATES_FOR_ANSWER:
        return _no_evidence()

    candidates_by_id = {c.chunk_id: c for c in candidates}
    # Computed from `candidates` directly, not from rerank's output — reranker.rerank()'s
    # own contract guarantees it never drops or adds a chunk_id, only reorders them, so
    # the SET of papers behind the candidate chunks is identical either way. That means
    # reranking and the Phase B audit+rank chain don't actually depend on each other at
    # all, even though they used to run strictly one after another — running them
    # concurrently below is a real wall-clock win with no change to what gets computed.
    unique_paper_ids = {c.paper_id for c in candidates}

    def _rank_papers() -> list[dict]:
        # Phase B — the expensive part — only now, only for papers that actually survived
        # into the candidate set. A paper live_search fetched but that never surfaced here
        # never gets classified or audited, and never costs that money (§5.8's logic,
        # applied synchronously instead of via a background worker).
        if live_contexts:
            live_search.audit_surviving_papers(unique_paper_ids, live_contexts)
        return ranking.rank(list(unique_paper_ids))

    rerank_input = [{"chunk_id": c.chunk_id, "text": c.text} for c in candidates]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rerank_future = pool.submit(reranker.rerank, research_query, rerank_input)
        rank_future = pool.submit(_rank_papers)
        reranked = rerank_future.result()
        paper_ranks = rank_future.result()

    ranked_ids_by_relevance = reranked.output.ranked_chunk_ids
    log.stage("rerank", f"reordered {len(ranked_ids_by_relevance)} chunk_ids", style="blue")
    paper_rank_order = {row["paper_id"]: i for i, row in enumerate(paper_ranks)}
    log.stage("rank", f"{len(paper_ranks)} papers ranked", style="blue")

    ranked_chunks = sorted(
        (candidates_by_id[cid] for cid in ranked_ids_by_relevance if cid in candidates_by_id),
        key=lambda c: paper_rank_order.get(c.paper_id, len(paper_rank_order)),
    )[:MAX_WRITER_CHUNKS]
    # Capped here — after BOTH relevance reranking and paper-quality ranking have already
    # ordered the full candidate set — not earlier. Real testing found response time
    # dominated in part by the writer processing every reranked chunk (up to ~20, each up
    # to 1500 chars) on every call, doubled again on a citation-check retry. Slicing the
    # final, fully-ordered list cuts that prompt size without skipping any of the
    # relevance/quality ordering logic itself. Real, accepted tradeoff for speed: fewer
    # chunks reaching the writer can occasionally mean fewer independent papers cited than
    # an uncapped run would have found.
    writer_input = [
        {"chunk_id": c.chunk_id, "paper_id": c.paper_id, "text": c.text} for c in ranked_chunks
    ]

    # Streamed — a live, unverified preview so the ~10-14s writer call (measured the
    # single biggest cost in a typical turn, see scripts/measure_pipeline_timing.py)
    # doesn't sit blank the whole time. Nothing shown via log.draft() is ever treated as
    # final — the real answer is still built the exact same way afterward, from
    # citation_checker-verified citations only (there's no regeneration retry anymore —
    # see the citation_checker call below — so this is now the only writer call a turn
    # ever makes).
    _drafted_sentence_indices: set[int] = set()
    _drafted_opening = False

    def _on_writer_partial(partial: dict) -> None:
        nonlocal _drafted_opening
        opening_text = partial.get("opening")
        if opening_text and not _drafted_opening:
            log.draft(opening_text)
            _drafted_opening = True
        for i, c in enumerate(partial.get("citations") or []):
            sentence = c.get("sentence") if isinstance(c, dict) else None
            if sentence and i not in _drafted_sentence_indices:
                log.draft(sentence)
                _drafted_sentence_indices.add(i)

    draft = writer.write(research_query, writer_input, on_partial=_on_writer_partial)
    opening = draft.output.opening
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
        # Renumbered consecutively from 1, always — not just after salvage. Real testing
        # showed a real answer displaying "[1]... [3]" with no [2]: salvage correctly
        # dropped a flagged citation_number 2, but kept the original (now gapped)
        # numbering on what survived. A missing number in the middle of a citation list
        # reads as a bug or a hidden citation, not as "one was safely removed" — there is
        # no legitimate reason for a reader-facing citation list to skip a number.
        verified_citations = [
            c.model_copy(update={"citation_number": i}) for i, c in enumerate(verified_citations, start=1)
        ]
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
    # Single pass, immediate salvage on any flag — no regeneration retry. This used to be
    # two attempts (flag -> full writer regeneration with the flags as feedback -> recheck
    # -> salvage only if STILL flagged), which real timing data showed costing ~8-12s
    # whenever it fired (a full second writer call plus a full second citation_checker
    # call) — the single biggest discretionary cost left in the pipeline once live search
    # stopped double-firing (see this function's live_search comment above). Explicit,
    # deliberate tradeoff, not a free win: this never shows unverified content either way
    # (salvage always drops what's flagged, exactly as before), but it no longer gives the
    # writer a chance to FIX a flagged citation before falling back to dropping it, so some
    # answers will carry fewer citations than the old two-attempt version would have kept.
    # Chosen explicitly over keeping the retry, to hold a hard ~30s ceiling on
    # practical_support rather than accept the old occasional 35-45s tail.
    mechanical_flags = citation_checker.check_mechanical(citations, supplied_chunks)
    flagged_numbers = {f.citation_number for f in mechanical_flags}
    verified = [c for c in citations if c.citation_number not in flagged_numbers]
    semantic_flags = citation_checker.check_semantic(verified) if verified else []

    all_flags = mechanical_flags + semantic_flags
    log.stage(
        "citation_checker",
        f"{len(all_flags)} flags",
        style="yellow" if all_flags else "green",
    )
    for f in all_flags:
        log.flag(f.reason, f.sentence, f.quote)
    if not all_flags:
        return _build_answered(citations)

    flagged_numbers = {f.citation_number for f in all_flags}
    salvaged_citations = [c for c in citations if c.citation_number not in flagged_numbers]
    if not salvaged_citations:
        return _no_evidence()
    log.warn(f"salvage: dropped {len(flagged_numbers)} flagged citation(s), kept {len(salvaged_citations)}")
    return _build_answered(salvaged_citations)
