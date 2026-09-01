"""Agent 6 — Translator. See docs/agents.md §6.

Query path, every turn where scope guard returns answerable. This is the enforced-in-
code privacy boundary (§7.2) — raw_input must not reach any code path past this agent's
output, including logs and external API calls. The caller must not pass raw_input
anywhere else; this prompt alone cannot guarantee that.

Short-term session memory (pipeline.py, agents/summarizer.py): this agent can optionally
receive prior context — a short rolling summary plus the last few turns' exact
research_query/reflection — to resolve a follow-up like "what about children" into a
complete, standalone query. That context is always already-scrubbed text the translator
itself produced on earlier turns, never raw_input from any turn, current or past — the
privacy boundary is about what can reach this step's OUTPUT, and prior outputs of this
same step were already safe to store.
"""

from pydantic import BaseModel

from neurodiversity.agents.base import AgentResult, run_agent

PROMPT_VERSION = "v4"

SYSTEM_PROMPT = """Convert this personal message into a researchable query, and write one reflection
sentence to show the person what you understood.

You may be given prior conversation context — a running summary and/or the last few
exchanges' research_query and reflection. Use it ONLY to resolve a follow-up that doesn't
stand on its own — e.g. if the prior topic was "post-social fatigue in autistic adults"
and the new message is just "what about children instead", the research_query should
become "post-social fatigue and recovery in autistic children", not just "children". If
the new message is already a complete, standalone question, ignore the context and
translate it as normal — do not let prior topics bleed into an unrelated new question.

First decide: is this message genuinely too ambiguous to form ANY reasonable
research_query, even using the conversation context above? This means it lacks a
referent entirely (e.g. "does it work" with no prior context establishing what "it" is),
not just that it could theoretically be read two ways. If the topic is reasonably
inferable — from the message itself or the conversation context — translate it normally;
do not ask for clarification just because a question is broad or informally phrased.

If it IS genuinely ambiguous: set needs_clarification to true, write a short, direct
clarifying_question, and give 2-4 concrete clarification_options representing the
plausible distinct interpretations (e.g. for "does it work", options might be about
different treatments or conditions the conversation could plausibly mean). Leave
research_query and reflection empty in this case — do not guess and translate anyway.

If it's NOT ambiguous, leave needs_clarification false and fill in:

research_query: a short, literature-search-style phrase capturing the topic and
population (e.g., "post-social fatigue and recovery in autistic adults"). Strip all
personal, identifying, or narrative detail — this query (and any conversation context
above) is the only thing that leaves this step; nothing else in the system ever sees the
original message. Specific numbers (a price, an age, a dose) should be dropped since a
paper won't mention them verbatim, but dropping a number must not change the SHAPE of the
question. A question about whether ONE specific treatment/program is worth pursuing
("should I treat my ADHD for $1000") must stay a question about that treatment's
effectiveness or evidence base — it must not turn into a broader multi-option comparison
("cost-effectiveness of ADHD treatment options") just because the number was dropped.
That changes what's actually being asked, not just how it's phrased: "is this treatment
worth it" and "which treatment is most cost-effective" are different questions, and
retrieval will search for the wrong thing if the translation quietly answers the second
one instead of the first.

reflection: one sentence, shown back to the person, that names what you understood their
question to be about — plainly, without diagnostic language, and without implying an
assessment of them. Do not soften or hedge; state the topic directly.

Do not answer the question. Do not add information not present in the original message or
the prior conversation context provided."""


class TranslationResult(BaseModel):
    needs_clarification: bool = False
    clarifying_question: str | None = None
    clarification_options: list[str] = []
    research_query: str = ""
    reflection: str = ""


def translate(raw_input: str, context_summary: str = "", recent_turns: list[tuple[str, str]] | None = None) -> AgentResult:
    """context_summary: running summary of turns older than the exact window (empty if
    none yet). recent_turns: (research_query, reflection) pairs for the last few turns,
    oldest first — both always already-scrubbed text, never raw_input."""
    user_message = raw_input
    if context_summary or recent_turns:
        context_block = ""
        if context_summary:
            context_block += f"Summary of earlier conversation: {context_summary}\n\n"
        if recent_turns:
            # recent_turns isn't research-only — chit-chat turns (agents/general_chat.py)
            # share this same memory window and have no separate reflection, just a topic
            # label in the first slot, so r can legitimately be None or equal to q.
            context_block += "Recent exchanges:\n" + "\n".join(
                f"- {q}" + (f" ({r})" if r and r != q else "") for q, r in recent_turns
            ) + "\n\n"
        user_message = f"{context_block}New message: {raw_input}"

    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        output_model=TranslationResult,
        prompt_version=PROMPT_VERSION,
        temperature=0.0,
    )
