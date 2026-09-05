"""Greeting responder. Not one of the original 11 (working spec §11) — added so a bare
"hi" gets a real, warm, on-brand response instead of falling through to out_of_domain's
cold boundary message.

Detection itself is scope_guard's model call, not plain code — a prior keyword/exact-match
fast path was removed from pipeline.py because greeting-or-not is a judgment call ("hy" vs
"hydroxyzine dosing"; a greeting with a real question attached vs one without) that only a
model call actually gets right in every case, not an approximation worth trading for speed.
This module is only the reply text, generated once scope_guard has already decided.

Tries a CASCADE of free OpenRouter models first (agents/base.py's run_agent_free_cascade),
falling back to the standard gpt-4o-mini path only if every one of them fails — the only
agent in this system currently doing this, and deliberately so: real, live testing (not
assumption) found every free OpenRouter model has at least one disqualifying defect for
tasks where accuracy matters (rate-limiting, malformed JSON, fabricated "research shows"
claims — see docs/agents.md and this session's evidence). Greeting is different: §8's own
docstring on GreetingTurn already calls it "the one place letting the model phrase freely
is safe" — there's no factual claim, no citation, nothing to fabricate, so a free model's
imperfection here has zero real consequence, unlike everywhere else those defects showed up.

Both `dots-studio/dots-3-note-preview:free` and `liquid/lfm-2.5-2.6b:free` individually
tested 7/7 clean on this exact prompt across separate test batches before being wired in —
the cascade tries dots-studio first (slightly better wording compliance, avoids the word
"research"), then liquid if that fails, before finally paying for gpt-4o-mini. A cascade
across free models only helps with AVAILABILITY (one rate-limited, try the next) — it does
not make a wrong answer more correct, which is exactly why this stays limited to the one
agent where a wrong answer has no real consequence.
"""

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_MINI, AgentResult, run_agent_free_cascade

PROMPT_VERSION = "v2"  # v2 = general self-description, no per-condition enumeration

FREE_MODELS = [
    "dots-studio/dots-3-note-preview:free",
    "liquid/lfm-2.5-2.6b:free",
]

SYSTEM_PROMPT = """The user just sent a plain greeting ("hi", "hello", "how are you") with no question
attached. Respond warmly and briefly — one or two short sentences. Introduce yourself simply and
generally as a tool that looks up what the published literature says for neurodivergent people —
do not list out specific conditions by name (no "autism, ADHD, dyslexia..." style enumeration); keep
it at that general level. Be plain that you can't diagnose or assess anyone, only share what the
literature shows. Keep it direct and concrete — avoid idioms, vague pleasantries, or
exclamation-heavy chipper phrasing — so the person knows exactly what to ask next."""


class GreetingOutput(BaseModel):
    message: str


def greet() -> AgentResult:
    return run_agent_free_cascade(
        system_prompt=SYSTEM_PROMPT,
        user_message="(greeting received, no further content)",
        output_model=GreetingOutput,
        prompt_version=PROMPT_VERSION,
        free_models=FREE_MODELS,
        fallback_model=MODEL_MINI,
        temperature=0.3,
    )
