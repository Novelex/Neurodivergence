"""Agent 5 — Scope guard. See docs/agents.md §5.

Query path, every turn, first step. Fails closed on ambiguity — the tie-break order
(distress > diagnostic_ask > out_of_domain > answerable) is what makes "ambiguous
routes to refuse, not to answer" (§7.1) enforceable rather than aspirational.
"""

from enum import Enum

from pydantic import BaseModel

from neurodiversity.agents.base import AgentResult, run_agent

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """Classify this message into exactly one category:

- answerable: a question researchable against the neurodevelopmental research literature
  (autism, ADHD, dyslexia, dyspraxia, Tourette's, and related conditions), not asking for
  a personal diagnosis or assessment.
- diagnostic_ask: asks this system to assess, diagnose, or predict whether the person (or
  someone they describe) has a condition, or to interpret their personal history against
  diagnostic criteria.
- distress: contains indicators of self-harm risk, acute hopelessness, or crisis-level
  language — not ordinary frustration, sadness, or the kind of exhaustion that is itself a
  valid research topic (e.g., autistic burnout).
- out_of_domain: not related to neurodevelopmental conditions or their research at all.

If the message is ambiguous between categories, prefer the more restrictive one in this
order: distress > diagnostic_ask > out_of_domain > answerable. Never resolve ambiguity by
choosing answerable."""


class ScopeClassification(str, Enum):
    answerable = "answerable"
    diagnostic_ask = "diagnostic_ask"
    distress = "distress"
    out_of_domain = "out_of_domain"


class ScopeResult(BaseModel):
    classification: ScopeClassification


def classify(raw_input: str) -> AgentResult:
    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=raw_input,
        output_model=ScopeResult,
        prompt_version=PROMPT_VERSION,
        temperature=0.0,
    )
