"""General chit-chat responder. Not one of the original 11 (working spec §11) — for a
message that's genuinely off-topic (out_of_domain per scope_guard) but is still an
ordinary conversational message, not a research question. Gives a normal, honest
chatbot-style reply instead of a flat "that's not what I cover" boundary message —
matching how any other chatbot handles small talk — while staying plain about what this
system is actually for, without repeating that reminder so often it becomes noise.

Never used for anything that could be mistaken for research content: this agent has no
access to any supplied chunks or citations, and its output never carries a citation
marker — it's a normal conversational reply, structurally incapable of being confused
with an evidence-backed answer.

Short-term session memory (pipeline.py, agents/summarizer.py): accepts the same
context_summary/recent_turns shape the translator does, so a chit-chat follow-up ("what
about in Pakistan") can resolve against what was just discussed instead of answering
blind. Real testing found this missing entirely — general chat had no memory wiring at
all, so every follow-up landed as a fresh, contextless message. Also returns a short
`topic` label (mirroring the translator's reflection) so pipeline.py can persist a memory
entry for chit-chat turns the same way it already does for research turns — recent_turns
isn't just for the research path.
"""

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_MINI, AgentResult, run_agent
from neurodiversity.agents.language_rules import LANGUAGE_RULES, LANGUAGE_RULES_VERSION

PROMPT_VERSION = f"v5-lang{LANGUAGE_RULES_VERSION}"  # v5 = explicit ban on unverified specific statistics

SYSTEM_PROMPT_BASE = """The user's message is unrelated to neurodevelopmental conditions or their research —
ordinary conversation, a general question, small talk. Reply the way any normal, helpful
chatbot would: direct, warm, genuinely useful for what they actually asked. You don't
need to mention what this system specializes in every time — only bring it up if it's
naturally relevant (e.g. they ask what you can help with, or the conversation drifts
somewhere you can actually be useful). Keep it brief and plain — no exclamation-heavy
chipper filler, no vague pleasantries.

You may be given prior conversation context — a running summary and/or the last few
exchanges. Use it to resolve a follow-up that doesn't stand on its own (e.g. if you were
just discussing noodle brands and the next message is "what about in Pakistan", answer
about noodle brands in Pakistan, not ask what topic they mean). If the new message is
already a complete, standalone message, answer it directly.

You have no supplied literature chunks and nothing you say here is checked against any
source — never state or imply a finding as fact ("studies show...", "evidence
indicates...", "has been shown to..."), even for a topic connected to autism/ADHD/etc.
that slipped into this path by mistake. This applies just as much to a SPECIFIC number you
feel confident about from training (a prevalence rate, a percentage, "1 in 44") as to a
vaguer claim — a specific-sounding statistic is not safer to state unverified, it's more
dangerous, because it reads as more authoritative than a vague one. If the person is
actually asking what the literature says about something, or asks for any statistic or
rate connected to a condition, say plainly that you'd need to look that up properly to
answer that honestly, rather than answering from general impression — this is a system
that verifies every claim against a real, cited source, and answering here would skip
that entirely.

Also write `topic`: a short label (a few words) naming what this exchange was about, for
your own future reference in later turns — not shown to the user."""

SYSTEM_PROMPT = f"{SYSTEM_PROMPT_BASE}\n{LANGUAGE_RULES}"


class ChatOutput(BaseModel):
    message: str
    topic: str


def reply(raw_input: str, context_summary: str = "", recent_turns: list[tuple[str, str]] | None = None) -> AgentResult:
    """context_summary/recent_turns: same shape as translator.translate's — short-term
    session memory, not limited to the research path."""
    user_message = raw_input
    if context_summary or recent_turns:
        context_block = ""
        if context_summary:
            context_block += f"Summary of earlier conversation: {context_summary}\n\n"
        if recent_turns:
            context_block += "Recent exchanges:\n" + "\n".join(
                f"- {q}" + (f" ({r})" if r and r != q else "") for q, r in recent_turns
            ) + "\n\n"
        user_message = f"{context_block}New message: {raw_input}"

    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        output_model=ChatOutput,
        prompt_version=PROMPT_VERSION,
        model=MODEL_MINI,
        temperature=0.3,
    )
