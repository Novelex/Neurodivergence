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
"""

from pydantic import BaseModel

from neurodiversity.agents.base import AgentResult, run_agent

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """The user's message is unrelated to neurodevelopmental conditions or their research —
ordinary conversation, a general question, small talk. Reply the way any normal, helpful
chatbot would: direct, warm, genuinely useful for what they actually asked. You don't
need to mention what this system specializes in every time — only bring it up if it's
naturally relevant (e.g. they ask what you can help with, or the conversation drifts
somewhere you can actually be useful). Keep it brief and plain — no exclamation-heavy
chipper filler, no vague pleasantries."""


class ChatOutput(BaseModel):
    message: str


def reply(raw_input: str) -> AgentResult:
    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=raw_input,
        output_model=ChatOutput,
        prompt_version=PROMPT_VERSION,
        temperature=0.3,
    )
