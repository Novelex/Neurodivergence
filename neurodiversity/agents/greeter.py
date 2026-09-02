"""Greeting responder. Not one of the original 11 (working spec §11) — added so a bare
"hi" gets a real, warm, on-brand response instead of either costing a full scope_guard
call or falling through to out_of_domain's cold boundary message.

Detection stays free (pipeline.py's _is_pure_greeting is plain code, no model call) — only
the reply text itself is generated, so it reads as a real response and not a hardcoded
string, while still costing next to nothing (one small, low-temperature call).
"""

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_MINI, AgentResult, run_agent

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """The user just sent a plain greeting ("hi", "hello", "how are you") with no question
attached. Respond warmly and briefly — one or two short sentences. Introduce yourself as
a tool that looks up what research says about autism, ADHD, dyslexia, dyspraxia, and
Tourette's, and be plain that you can't diagnose or assess anyone, only share what the
literature shows. Keep it direct and concrete — avoid idioms, vague pleasantries, or
exclamation-heavy chipper phrasing — so the person knows exactly what to ask next."""


class GreetingOutput(BaseModel):
    message: str


def greet() -> AgentResult:
    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message="(greeting received, no further content)",
        output_model=GreetingOutput,
        prompt_version=PROMPT_VERSION,
        model=MODEL_MINI,
        temperature=0.3,
    )
