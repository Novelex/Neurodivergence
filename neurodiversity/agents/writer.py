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

from pydantic import BaseModel

from neurodiversity.agents.base import AgentResult, run_agent

PROMPT_VERSION = "v4"

SYSTEM_PROMPT = """Write a prose answer to the user's research question using only the supplied chunks below.
The chunks are already ordered by evidential strength — do not re-rank them, re-order them,
or second-guess their order; that judgement has already been made upstream.

Every factual claim in your answer must trace to specific supplied chunks. Do not
introduce information, studies, or figures not present in the supplied material.

Cite inline as you write: after each factual sentence, insert a bracketed number like
[1], [2] matching that sentence's position in the citations list you output. Number
citations in the order they first appear in the prose, starting at 1. A reader should be
able to see which specific claim each citation backs without leaving the paragraph.

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

For each factual sentence you write, also record: the sentence itself exactly as it
appears in your prose (verbatim, including its [N] marker), and the full list of quotes
(each with its chunk_id and paper_id) that together support it — one quote if the claim
comes from one source, more than one if it genuinely synthesizes several. The
citation_number must match the [N] marker you placed inline in the prose for that claim.

Also write one short, separate opening sentence — plain and direct, not a factual claim,
no citation needed or wanted. It briefly acknowledges the person's question before the
evidence starts (e.g. "That's a reasonable thing to weigh up." or "That's worth looking
into."). Keep it short, concrete, and non-generic to what was actually asked — avoid vague
pleasantries, exclamation marks, or chipper filler ("Great question!"). Do not restate the
question itself (that's already shown separately) and do not preview what the evidence
will say — it is a brief acknowledgment, not a summary."""


class QuoteRef(BaseModel):
    paper_id: str
    chunk_id: str
    quote: str


class Citation(BaseModel):
    citation_number: int
    sentence: str
    supporting_quotes: list[QuoteRef]


class WriterOutput(BaseModel):
    opening: str
    prose: str
    citations: list[Citation]


def write(
    research_query: str,
    ranked_chunks: list[dict],
    previous_flags: list[tuple[str, str, str]] | None = None,
) -> AgentResult:
    """ranked_chunks: list of {"chunk_id", "paper_id", "text"}, already in rank order.

    previous_flags: (sentence, quotes_joined, reason) triples from a prior citation-check
    failure, working spec §7.6's "the writer is told which specific claim was
    unsupported and regenerates" — the retry must actually convey what was wrong, not
    just re-roll the same call at temperature 0.2 and hope.
    """
    chunks_block = "\n\n".join(
        f"chunk_id: {c['chunk_id']}\npaper_id: {c['paper_id']}\ntext: {c['text']}"
        for c in ranked_chunks
    )
    user_message = f"Research question: {research_query}\n\nSupplied chunks:\n\n{chunks_block}"

    if previous_flags:
        flags_block = "\n".join(
            f'- Your sentence: "{sentence}"\n  Cited quote(s): "{quotes}"\n  Problem: {reason}'
            for sentence, quotes, reason in previous_flags
        )
        user_message = (
            f"{user_message}\n\n"
            "Your previous draft had these specific sentences flagged as unsupported or "
            "misrepresenting their cited source. Fix each one — either add the additional "
            "quote(s) the claim actually needs, correct the claim to match what the cited "
            "quotes say, or remove the claim entirely if nothing supplied backs it:\n\n"
            f"{flags_block}"
        )

    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        output_model=WriterOutput,
        prompt_version=PROMPT_VERSION,
        # No model= override — uses run_agent's gpt-4o default. See module docstring.
        temperature=0.0,
    )
