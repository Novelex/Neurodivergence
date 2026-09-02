"""Session-memory summarizer. Not one of the original 11 (working spec §11) — supports
short-term session memory: a rolling window of the last few turns stays exact (their
research_query/reflection, already stored in the turns table), and this agent folds a
turn OUT of that window into a short running summary as it ages out, one turn at a time.

Never called per-turn — only when a turn is about to fall out of the exact window, so the
recurring cost is small and infrequent rather than a per-turn tax. Input is always
already-scrubbed research_query/reflection text, never raw_input — the same §7.2 privacy
boundary applies to what this agent can see as everywhere else in the system.
"""

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_NANO, AgentResult, run_agent

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You maintain a short running summary of a research conversation so far. You are given
the existing summary (empty if this is the first fold) and one additional exchange
(research_query + reflection) to fold into it.

Write an updated summary, 2-4 sentences maximum, capturing the topics and threads covered
so far — plainly, no diagnostic language, no speculation about the person. If the new
exchange is a natural continuation of an existing thread, merge them rather than listing
both separately. If space is tight, prioritize recency and drop earlier detail that's no
longer load-bearing for understanding a follow-up question — this summary exists only to
let a later message like "what about children" resolve to the right topic, not to be a
complete transcript."""


class SummaryOutput(BaseModel):
    summary: str


def fold(existing_summary: str, research_query: str, reflection: str) -> AgentResult:
    user_message = (
        f"Existing summary: {existing_summary or '(none yet)'}\n\n"
        f"Exchange to fold in:\nresearch_query: {research_query}\nreflection: {reflection}"
    )
    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        output_model=SummaryOutput,
        prompt_version=PROMPT_VERSION,
        model=MODEL_NANO,
        temperature=0.0,
    )
