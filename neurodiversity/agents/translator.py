"""Agent 6 — Translator. See docs/agents.md §6.

Query path, every turn where scope guard returns answerable. This is the enforced-in-
code privacy boundary (§7.2) — raw_input must not reach any code path past this agent's
output, including logs and external API calls. The caller must not pass raw_input
anywhere else; this prompt alone cannot guarantee that.
"""

from pydantic import BaseModel

from neurodiversity.agents.base import AgentResult, run_agent

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """Convert this personal message into a researchable query, and write one reflection
sentence to show the person what you understood.

research_query: a short, literature-search-style phrase capturing the topic and
population (e.g., "post-social fatigue and recovery in autistic adults"). Strip all
personal, identifying, or narrative detail — this query is the only thing that leaves this
step; nothing else in the system ever sees the original message.

reflection: one sentence, shown back to the person, that names what you understood their
question to be about — plainly, without diagnostic language, and without implying an
assessment of them. Do not soften or hedge; state the topic directly.

Do not answer the question. Do not add information not present in the original message."""


class TranslationResult(BaseModel):
    research_query: str
    reflection: str


def translate(raw_input: str) -> AgentResult:
    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=raw_input,
        output_model=TranslationResult,
        prompt_version=PROMPT_VERSION,
        temperature=0.0,
    )
