"""Query broadener. Not one of the original 11 (working spec §11) — widens a too-narrow
research_query one step at a time before the pipeline ever falls back to no_evidence.

Real observation motivating this: genuinely zero relevant literature is rare. The more
common failure is a research_query specific enough that retrieval and live search don't
surface what does exist on the wider topic — not that nothing exists at all. Widening the
search is the honest way to reduce false no_evidence outcomes; manufacturing an answer
when a search is exhausted is not (query/pipeline.py's broadening loop still falls back to
no_evidence, honestly, if even a widened search finds nothing real to cite).
"""

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_MINI, AgentResult, run_agent

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """The given research_query returned too little relevant literature. Produce a broader
version of it — one meaningful step out, not an unrelated topic. Keep the same
population/condition where one is given; widen the specific mechanism, treatment, claim,
or angle to its parent category. For example: "efficacy of a specific $1000 ADHD
coaching program" -> "efficacy and cost of ADHD coaching and behavioral interventions";
"cost-effectiveness of ADHD treatment options" -> "ADHD treatment access and
affordability". Do not widen so far that the query loses connection to what was actually
asked — this is one step broader, repeatable, not a jump to the whole domain at once."""


class BroadenOutput(BaseModel):
    broadened_query: str


def broaden(research_query: str) -> AgentResult:
    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=f"Too-narrow research_query: {research_query}",
        output_model=BroadenOutput,
        prompt_version=PROMPT_VERSION,
        model=MODEL_MINI,
        temperature=0.0,
    )
