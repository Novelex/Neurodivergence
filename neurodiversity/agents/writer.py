"""Agent 8 — Writer. See docs/agents.md §8.

Query path. Originally run at temp 0.2 (working spec §11's one deliberate non-zero
exception, for phrasing variety) — moved to 0 after real testing showed it re-inserting
the same fabricated, uncited specific (a named substructure, a measurement) on a citation
retry even after being told exactly which detail was wrong. At temp 0, phrasing is more
mechanical, but the model no longer had that same room to embellish a thin citation with
"known" facts from training instead of what the quote actually says.
Produces prose from supplied chunks only; ranking is not its concern. Applies the
defamation-safe phrasing rule (§7.5) when a chunk names a commercial product or
provider: state the regulatory record as fact, never a conclusion about intent.

Runs on gpt-4o, not the gpt-4o-mini used for most other agents — reverted after a real,
reproducible failure: a query on "strategies for managing ADHD symptoms" (a topic with
abundant genuine literature) returned no_evidence because 6/6 citations failed the
MECHANICAL check (plain-code exact substring match, not a judgment call) — the model was
producing quotes that were close paraphrases of the source text, not byte-for-byte
copies, on both the original attempt and the retry. This is a precision/copying task, not
a judgment task, and gpt-4o-mini was not reliable enough at it even with real,
high-quality source material available.
"""

from typing import Callable

from pydantic import BaseModel

from neurodiversity.agents.base import AgentResult, run_agent, run_agent_stream
from neurodiversity.agents.language_rules import LANGUAGE_RULES, LANGUAGE_RULES_VERSION

PROMPT_VERSION = f"v7-lang{LANGUAGE_RULES_VERSION}"  # v7 = no invented numbers; keep qualitative-study framing

SYSTEM_PROMPT_BASE = """Answer the user's research question using only the supplied chunks below, composed
directly as an ordered list of cited sentences — not as a separate paragraph you write first and then
break apart. The chunks are already ordered by evidential strength — do not re-rank them, re-order
them, or second-guess their order; that judgement has already been made upstream.

Every factual claim in your answer must trace to specific supplied chunks. Do not
introduce information, studies, or figures not present in the supplied material.

Each citations entry is one sentence of the final answer. Set citation_number to the order
these sentences should be read in, starting at 1 — the reader-facing bracket number is
added separately from this field, so do not write "[1]" or any bracket into the sentence
text itself, just the plain sentence.

This system routinely answers by synthesizing several papers. A sentence that genuinely
draws on more than one supplied chunk is fine and expected — cite ALL of the quotes it
draws on together, under that one citation_number, rather than picking just one of them.
The failure this causes when done wrong is a sentence combining two or three findings
into one broader claim while citing only one supporting quote — for example, writing "a
network of regions including the thalamus, basal ganglia, and OFC" but only citing the
OFC finding. The fix is not to avoid synthesis; it's to cite everything the sentence
actually draws on:
- If a sentence states two facts from two different chunks, list both of those chunks'
  quotes as supporting_quotes for that one citation — don't force an artificial split
  into separate sentences, and don't drop one of the sources to keep the citation simple.
- Never add a specific detail (a mechanism, a broader category, an implied cause) that
  isn't explicitly present in at least one of the quotes you cite for that sentence, even
  if it sounds like a reasonable inference from the surrounding material.
- Never narrow a general structure a quote names (e.g. "thalamus") down to a specific
  substructure (e.g. "pulvinar nucleus") unless that specific term appears in the quote
  itself — you may know the real anatomy, but if the quote didn't name it, you don't cite
  it. The same applies to any other specific mechanism, measurement, or subtype: if it is
  not the quote's own wording, it does not go in the sentence.
- Preserve the quote's own certainty level. If a quote hedges ("may support", "proposed",
  "potential", "one small trial", "did not reach significance"), your sentence must keep
  that same hedge — do not upgrade a tentative or proposed finding into a stated fact, and
  do not drop a quote's stated caveat or contradictory follow-up when summarizing it.
- Never state a number, percentage, or fraction ("almost half", "70%", "one in three")
  that is not the quote's own figure, verbatim. A plausible-sounding number you recall
  from training is not a citable fact — if the quote doesn't contain that number, the
  sentence doesn't either.
- If a quote describes what STUDY PARTICIPANTS said, did, or reported (qualitative
  research — "participants described...", "interviewees noted..."), keep that framing.
  Do not generalize it into an unqualified claim about the broader population ("autistic
  adults often report...", "people with ADHD tend to...") — what a study's participants
  said is evidence about them, not yet a general population claim, and stripping the
  qualifier is exactly the kind of overstatement citation-checking exists to catch.

If the supplied chunks discuss a specific named commercial product, clinic, or provider,
state the regulatory record and evidence status as fact (e.g., "a 510(k) clearance
establishes substantial equivalence to a predicate device, not diagnostic validity — no
accuracy data was submitted") and never state a conclusion about that party's intent (e.g.,
never call something a "scam" or accuse it of deception). The regulatory record makes the
point; you do not need to add a judgement about intent to make it.

Report null findings and thin evidence honestly. Do not smooth over a paper's limitations
to make the answer sound more conclusive than the evidence supports.

Some research_query values ask about diagnostic criteria or symptom overlap (e.g. "ADHD
diagnostic criteria and symptom presentation in adults"). Answer these exactly like any
other evidence question — describe what the criteria/literature say in general terms —
but never phrase a sentence as a verdict about a specific person ("you have ADHD", "this
means you're autistic"). You were never given any personal information to make that call
with in the first place (only a scrubbed research_query and literature chunks reach you),
so this should already be structurally impossible — this is a backstop, not a hedge on
otherwise-personal content.

For each sentence, also record the full list of quotes (each with its chunk_id and
paper_id) that together support it — one quote if the claim comes from one source, more
than one if it genuinely synthesizes several.

Also write one short, separate opening sentence — plain and direct, not a factual claim,
no citation needed or wanted. It briefly acknowledges the person's question before the
evidence starts (e.g. "That's a reasonable thing to weigh up." or "That's worth looking
into."). Keep it short, concrete, and non-generic to what was actually asked — avoid vague
pleasantries, exclamation marks, or chipper filler ("Great question!"). Do not restate the
question itself (that's already shown separately) and do not preview what the evidence
will say — it is a brief acknowledgment, not a summary."""

SYSTEM_PROMPT = f"{SYSTEM_PROMPT_BASE}\n{LANGUAGE_RULES}"


class QuoteRef(BaseModel):
    paper_id: str
    chunk_id: str
    quote: str


class Citation(BaseModel):
    citation_number: int
    sentence: str
    supporting_quotes: list[QuoteRef]


class WriterOutput(BaseModel):
    """No separate `prose` field — a prior version had the model write the whole answer
    as one flowing paragraph AND repeat it broken into citations, and only the citations
    ever reached the screen (pipeline.py's _render_prose rebuilds the displayed text
    purely from citations[].sentence — see its own docstring for why). The paragraph was
    pure wasted generation: the model wrote the full answer twice, and only field
    declaration order determines structured-output generation order, so it also fully
    blocked citations (and any streaming preview of them) from starting until an unused
    field finished. Field order matters here: opening first (it's what a live preview
    shows immediately), then citations."""

    opening: str
    citations: list[Citation]


def write(
    research_query: str,
    ranked_chunks: list[dict],
    on_partial: Callable[[dict], None] | None = None,
) -> AgentResult:
    """ranked_chunks: list of {"chunk_id", "paper_id", "text"}, already in rank order.

    on_partial: forwarded as-is to run_agent_stream: a raw partial dict, not a validated
    WriterOutput, and never itself checked or final — see that function's docstring. The
    final AgentResult returned here is identical either way.

    No retry-with-feedback path anymore — pipeline.py's citation_checker step now salvages
    (drops a flagged citation, keeps the rest) on the first and only attempt rather than
    regenerating with the flags as feedback. That regeneration-and-recheck cycle cost
    ~8-12s whenever it fired (a full second call to this function plus a full second
    citation_checker pass) — the biggest discretionary latency cost left once live search
    stopped double-firing. Real, deliberate tradeoff: some answers now carry fewer
    citations than a successful retry would have kept, in exchange for a hard ceiling on
    total turn time. See pipeline.py's _search_and_write for where this is decided."""
    chunks_block = "\n\n".join(
        f"chunk_id: {c['chunk_id']}\npaper_id: {c['paper_id']}\ntext: {c['text']}"
        for c in ranked_chunks
    )
    user_message = f"Research question: {research_query}\n\nSupplied chunks:\n\n{chunks_block}"

    run = run_agent_stream if on_partial is not None else run_agent
    kwargs = {"on_partial": on_partial} if on_partial is not None else {}
    return run(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        output_model=WriterOutput,
        prompt_version=PROMPT_VERSION,
        # No model= override — uses run_agent's/run_agent_stream's gpt-4o default. See
        # module docstring.
        temperature=0.0,
        **kwargs,
    )
