"""Agent 9 — Citation checking. See docs/agents.md §9, working spec §7.6.

Two layers, run in order:
  9a. Mechanical check (plain code, no model): every citation's chunk_ids must be in the
      supplied set, and each of its quotes must appear verbatim in its own chunk's text.
      Exact membership/substring tests only.
  9b. Semantic-fidelity agent (gpt-4o, temp 0): runs only on citations that passed 9a —
      does the sentence fairly represent the COMBINATION of all its supporting quotes,
      not whether any single quote exists (already answered by 9a).

A citation can carry more than one supporting quote — a sentence that genuinely
synthesizes two findings should cite both, not be forced into an artificial 1:1
sentence-to-quote mapping. Forcing that mapping was the real bug behind a recurring
failure: the writer would merge two facts into one sentence but cite only one of them,
and the checker had no way to represent "this sentence legitimately needs both quotes."

Remediation (either layer): one retry, writer regenerates using only supplied chunks. If
the retry still has a flagged claim, the turn ends at no_evidence. Capped at one attempt
— an uncapped retry loop here is the same pattern §2.5 rules out elsewhere.

9b reverted to gpt-4o (from gpt-4o-mini) alongside the writer — real testing on the same
failure (a "strategies for managing ADHD symptoms" query with genuinely good literature
available) showed the semantic layer producing a self-contradictory flag: reason text
reading "No fidelity failure; sentence accurately restates the quote," attached to a
citation it had just flagged. This is the actual safety net against fabricated or
overstated claims — not the layer to keep on the model that already failed the mechanical
check on the same real turn.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from neurodiversity.agents.base import run_agent

PROMPT_VERSION = "v4"

SYSTEM_PROMPT = """You are given (citation_number, sentence, quotes) groups from a draft answer — each
sentence paired with all the quotes it cites together as support (already confirmed to
exist verbatim in their sources — you do not need to re-check that). Your only job is
fidelity: does the sentence fairly represent what the quotes, taken together, actually
say — or does it overstate, understate, add a detail present in none of them, or combine
them into a claim broader than what they jointly support?

A sentence citing two quotes together is fine and expected if it's genuinely
synthesizing both — do not flag a sentence just for combining multiple sources. Flag it
only if the combined claim goes beyond what the cited quotes, together, actually say:
not for style, phrasing, or whether you'd have written it differently. A cautious quote
("no significant difference in one small trial") paired with an overstated sentence
("research conclusively shows X doesn't work") is a fidelity failure. A sentence that
accurately synthesizes two quotes into one claim, with nothing added beyond what's in
either of them, is not.

If the quote itself already states a finding plainly, as an unhedged fact ("decreased WM
volume was observed in this region"), a sentence that restates that same finding plainly
is NOT overstatement — it is only overstatement to state something MORE strongly or MORE
certainly than the quote itself does. Do not flag a sentence merely for being phrased
differently, more concisely, or without repeating the quote's own supporting detail
(e.g. which prior studies agreed) — that is restatement, not overstatement. Reserve a
flag for one of these three things only: (1) the sentence upgrades language the quote
itself hedges ("may", "proposed", "one small study") into unconditional certainty the
quote does not claim; (2) the sentence states a specific detail — a substructure, a
mechanism, a number — that is not the quote's own wording, anywhere in the quotes cited;
(3) the sentence omits a caveat or contradiction that is central to the quote's own
finding, such that the sentence's claim reverses or inverts what the quote actually
concluded. A sentence that plainly restates a fact the quote itself already states as
fact is not a fidelity failure, even if worded more simply.

For each flagged group, output its citation_number exactly as given, and a one-phrase
reason. Do not re-transcribe the sentence or quotes yourself — reference them only by
citation_number."""


@dataclass
class Flag:
    citation_number: int
    sentence: str
    quote: str  # joined with " | " if the citation had multiple supporting quotes
    reason: str


class _SemanticFlagRef(BaseModel):
    citation_number: int
    reason: str


class _SemanticCheckOutput(BaseModel):
    flagged: list[_SemanticFlagRef] = []


def check_mechanical(citations: list, supplied_chunks: list[dict]) -> list[Flag]:
    """9a — plain code, no model. citations: writer.Citation objects, each with a
    supporting_quotes list. Every quote must exist verbatim in its own chunk_id."""
    supplied_by_id = {c["chunk_id"]: c["text"] for c in supplied_chunks}
    flags = []
    for citation in citations:
        joined_quotes = " | ".join(q.quote for q in citation.supporting_quotes)
        for q in citation.supporting_quotes:
            if q.chunk_id not in supplied_by_id:
                flags.append(Flag(citation_number=citation.citation_number, sentence=citation.sentence, quote=joined_quotes, reason=f"chunk_id {q.chunk_id!r} not in supplied set"))
                break
            elif q.quote not in supplied_by_id[q.chunk_id]:
                flags.append(Flag(citation_number=citation.citation_number, sentence=citation.sentence, quote=joined_quotes, reason="quote not found verbatim in its cited chunk"))
                break
    return flags


def check_semantic(verified_citations: list) -> list[Flag]:
    """9b — only called on citations that passed 9a. Each sentence judged against the
    full combination of quotes it cited, not one at a time.

    The model is asked to reference a flagged group only by citation_number, not to
    re-transcribe its sentence/quote text — an LLM asked to echo a long text span back
    verbatim does not reliably do so byte-for-byte (confirmed by real testing: it
    sometimes drops the inline [N] marker, sometimes keeps it), and matching on that
    unreliable text downstream caused a flagged citation to survive into the final
    answer with its bracket marker still in the prose. A citation_number is something
    the model can reliably reproduce exactly.
    """
    by_number = {c.citation_number: c for c in verified_citations}
    pairs_block = "\n\n".join(
        f"citation_number: {c.citation_number}\nsentence: {c.sentence}\nquotes: "
        + " | ".join(q.quote for q in c.supporting_quotes)
        for c in verified_citations
    )
    result = run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=pairs_block,
        output_model=_SemanticCheckOutput,
        prompt_version=PROMPT_VERSION,
        # No model= override — uses run_agent's gpt-4o default. See module docstring.
        temperature=0.0,
    )
    flags = []
    for ref in result.output.flagged:
        citation = by_number.get(ref.citation_number)
        if citation is None:
            continue  # model referenced a citation_number that wasn't in the input; ignore rather than crash
        joined_quotes = " | ".join(q.quote for q in citation.supporting_quotes)
        flags.append(Flag(citation_number=citation.citation_number, sentence=citation.sentence, quote=joined_quotes, reason=ref.reason))
    return flags
