"""Agent 5 — Scope guard. See docs/agents.md §5.

Query path, every turn, first step. Fails closed on ambiguity — the tie-break order
(distress > diagnostic_ask > practical_support > greeting > out_of_domain > answerable) is
what makes "ambiguous routes to refuse, not to answer" (§7.1) enforceable rather than
aspirational.

practical_support exists because a flat out_of_domain boundary message is a dead end for
a real, non-research need clearly tied to being autistic/ADHD/etc. — workplace rights,
discrimination, education accommodations, benefits — that this system can't answer from
the literature but shouldn't just bounce with nothing. Real testing case: "I am autistic
and need guidance about the law on office harassment" is not researchable, not a
diagnostic ask, and not distress by itself, but a bare "that's not what I cover" response
is a worse failure than pointing to real, named organizations that actually handle this.

greeting was originally a plain-code keyword match (no model call) — dropped after real
testing showed it fails on anything not in its exact list ("hy" instead of "hi" fell
through to out_of_domain). Folded into this same classification call instead: the model
already has to read the message anyway, and recognizing a greeting — typos, variants, and
all — is exactly the kind of judgment call a keyword list can't make but a model can.
"""

from enum import Enum

from pydantic import BaseModel

from neurodiversity.agents.base import AgentResult, run_agent

PROMPT_VERSION = "v5"

SYSTEM_PROMPT = """Classify this message into exactly one category:

- answerable: a question researchable against the neurodevelopmental research literature
  (autism, ADHD, dyslexia, dyspraxia, Tourette's, and related conditions), not asking for
  a personal diagnosis or assessment. A condition the person mentions having is background
  context here, not a request — e.g. "I have ADHD, is there evidence this £1200 program
  actually cures it?" is answerable: the person states their diagnosis as a given fact and
  asks an evidence question about a specific claim, not for an assessment of themselves.
  This also covers a treatment-decision question that never explicitly says "I have X" —
  e.g. "if I should treat ADHD for $1000" is answerable, not diagnostic_ask: the question
  is whether a $1000 treatment is worth it or evidence-backed, not whether the person has
  ADHD in the first place. Evaluating a treatment, program, or cost is answerable even
  without an explicit diagnosis disclosure, as long as the question is about the
  treatment's legitimacy or evidence, not about determining whether the person has the
  condition.
- diagnostic_ask: asks this system to assess, diagnose, or predict whether the person (or
  someone they describe) HAS a condition, or to interpret their personal history/symptoms
  against diagnostic criteria to reach a conclusion about them — e.g. "do I have ADHD",
  "does this sound like autism to you", "am I dyslexic based on X". The distinguishing
  question: is the person asking the system to determine something about THEM (whether
  they have a condition, what's "wrong" with them), or asking about a treatment, program,
  or claim's legitimacy? Only the former is diagnostic_ask — asking whether a treatment is
  worth its cost or backed by evidence is a question about the treatment, not the person,
  even when phrased in the first person ("should I treat my ADHD" is about the treatment
  decision, not a request to be diagnosed).
- distress: contains indicators of self-harm risk, acute hopelessness, or crisis-level
  language — not ordinary frustration, sadness, or the kind of exhaustion that is itself a
  valid research topic (e.g., autistic burnout).
- practical_support: a real, practical need connected to being autistic/ADHD/dyslexic/
  dyspraxic/having Tourette's that is NOT researchable against the literature and NOT a
  request for diagnosis — workplace rights or discrimination, harassment, education
  accommodations, benefits or disability support, and similar life-practical questions.
  When this fires, also set practical_topic to whichever of these fits best: "workplace",
  "education", "benefits", or "general" (use "general" only if none of the other three
  clearly fits). e.g. "I am autistic and need guidance about the law on office harassment"
  is practical_support with practical_topic "workplace" — not out_of_domain, because it is
  clearly tied to the person's neurodevelopmental condition even though it isn't a
  research question, and not answerable, because no literature search answers it.
- greeting: the ENTIRE message is just a greeting or pleasantry with no other content —
  "hi", "hello", typos/variants of these ("hy", "helo"), "how are you", "thanks", "bye" —
  and nothing else is being asked. A greeting attached to a real question is NOT this
  category — "hi, what does research say about X" is answerable, not greeting, because
  there's a real question to answer. Only classify as greeting when there is nothing else
  to respond to.
- out_of_domain: not related to neurodevelopmental conditions at all — not the research,
  and not a practical need connected to having one either — and not just a greeting either.

If the message is ambiguous between categories, prefer the more restrictive one in this
order: distress > diagnostic_ask > practical_support > greeting > out_of_domain >
answerable. Never resolve ambiguity by choosing answerable. This does not make a stated
diagnosis ambiguous by itself — ambiguity means genuine uncertainty about which category
fits, not the mere presence of a personal disclosure alongside an otherwise clear,
researchable question."""


class ScopeClassification(str, Enum):
    answerable = "answerable"
    diagnostic_ask = "diagnostic_ask"
    distress = "distress"
    practical_support = "practical_support"
    greeting = "greeting"
    out_of_domain = "out_of_domain"


class PracticalTopic(str, Enum):
    workplace = "workplace"
    education = "education"
    benefits = "benefits"
    general = "general"


class ScopeResult(BaseModel):
    classification: ScopeClassification
    practical_topic: PracticalTopic | None = None


def classify(raw_input: str) -> AgentResult:
    return run_agent(
        system_prompt=SYSTEM_PROMPT,
        user_message=raw_input,
        output_model=ScopeResult,
        prompt_version=PROMPT_VERSION,
        temperature=0.0,
    )
