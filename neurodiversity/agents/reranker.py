"""Reranker — not one of the 11 agents. See docs/agents.md, working spec §7.3.

Query path, between retrieve and the deterministic SQL rank. Temp 0, prompted for
relevance ordering only — never quality. Quality ordering stays entirely in
query/ranking.py; this call must never be influenced by anything that owns.

Moved to the smaller mini model (from gpt-4o) for latency — this is a single relevance
signal, not the final word: the deterministic SQL quality rank and the writer's own
citation discipline both come after it, so a slightly less sharp ordering here doesn't
compromise the answer's correctness the way a mistake in the writer or citation checker
would.
"""

from pydantic import BaseModel

from neurodiversity.agents.base import MODEL_NANO, AgentResult, run_agent

PROMPT_VERSION = "v1"

SYSTEM_PROMPT_TEMPLATE = """Reorder these candidate passages by how directly relevant they are to a research
question. Nothing else.

Research question: {research_query}

Judge topical relevance only — does this passage actually address the question. Do not
reorder by the study's sample size, methodology, or how trustworthy the finding seems;
that judgement happens in a separate step downstream and is not your job here. A highly
relevant passage from a weak study still ranks above an irrelevant passage from a strong
one at this step.

Output every chunk_id from the input exactly once, reordered from most to least relevant.
Do not drop, duplicate, or invent any chunk_id."""


class RerankResult(BaseModel):
    ranked_chunk_ids: list[str]


def rerank(research_query: str, candidates: list[dict]) -> AgentResult:
    """candidates: list of {"chunk_id": str, "text": str}."""
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(research_query=research_query)
    candidates_block = "\n\n".join(
        f"chunk_id: {c['chunk_id']}\ntext: {c['text'][:800]}" for c in candidates
    )
    return run_agent(
        system_prompt=system_prompt,
        user_message=candidates_block,
        output_model=RerankResult,
        prompt_version=PROMPT_VERSION,
        model=MODEL_NANO,
        temperature=0.0,
    )
